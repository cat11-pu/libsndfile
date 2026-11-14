# libsndfile 读取器健壮性与等价性测试报告

- 被测对象：`libsndfile`（commit `396a715d`），静态库构建
- 测试日期：2026-11-14
- 测试机：Ubuntu 26.04，GCC 15.2，16 核
- 结论：**3025 个畸形输入零崩溃 / 零越界 / 零泄漏，全部失败带字节偏移；500 个合法文件与参考实现逐样本完全一致（2,615,405 个 float 样本，0 差异）。**

## 1. 测试方法

### 1.1 两个独立构建

| 构建 | 配置 | 用途 |
| --- | --- | --- |
| `build-asan` | `-O1 -g -fsanitize=address,undefined`，静态库，LSan 随 ASan 启用 | 崩溃 / 越界 / UB / 泄漏检测 |
| `build-ref` | `-O2` Release，静态库，无 sanitizer | 参考实现，快速最小化与对照解码 |

两构建来自同一份源码、同一套编译选项（除 sanitizer/优化级别外），保证差异仅来自检测手段。

### 1.2 虚拟 IO 与偏移追踪

所有输入都通过内存虚拟 IO（`sf_open_virtual`）喂给读取器，不触碰真实文件路径。
`fuzz/vio_track.h` 在每个 `read`/`seek` 回调里记录读取器访问到的最高字节偏移
`max_access`（exclusive 上界），并对越界 seek/read 做钳制。这样：

- 每个失败都能定位到读取器实际推进到的字节偏移；
- ASan 在库内部负责真实内存安全校验，虚拟 IO 层负责边界钳制与偏移记录，二者互补。

Sanitizer 有效性已用独立探针验证：堆越界探针触发
`AddressSanitizer: heap-buffer-overflow`（退出码 99），泄漏探针触发
`LeakSanitizer: detected memory leaks`（退出码 99），证明“零问题”不是因为检测器未生效。

### 1.3 畸形语料（3000 变异 + 25 定向边界）

由 `fuzz/gen_malformed.py` 从 120 个跨格式合法种子确定性变异生成（固定随机种子，可复现）：

| 类别 | 数量 | 覆盖内容 |
| --- | --- | --- |
| `trunc` | 486 | 头/块中/末字节等多偏移截断，含 0、1 字节 |
| `field` | 718 | 头字段清零、相邻字段交换、字段错位、端序翻转 |
| `size` | 360 | 长度/尺寸/计数字段写入 32 位极值 |
| `enc` | 634 | 非法 format/subtype 编码、保留字、非法 magic/form 标签 |
| `bit` / `byte` | 513 | 单位/多位翻转、字节插入/删除/重复 |
| `chaos` | 289 | 突发损坏、头洗牌、垃圾追加、全 0/全 0xFF、纯随机、伪 magic |

另有 `fuzz/gen_edge.py` 生成的 22 个手工定向案例，外加 3 个空/极短输入探针，共 25 个：64 位 `0xFFFF…FFFF` 块长、
32 位溢出、声明 4GB 尺寸、巨型声道数（最大 `0x7FFFFFFF`）、头/负载长度不一致、
W64 的 64 位 GUID 长度溢出、CAF/AIFF 的巨型尺寸字段。

### 1.4 合法语料与逐样本比对（500 个）

`fuzz/gen_valid.py` 经系统 libsndfile（ctypes）写出 500 个合法文件，覆盖 **47 种
容器×子类型组合**（WAV/WAVE/W64/AIFF/AU/CAF/FLAC/OGG-Vorbis/VOC/IRCAM/NIST/SVX/
PVF/XI/HTK/SDS/AVR/WVE/RAW；PCM 8/16/24/32、u8、float/double、μ-law/A-law、
IMA/MS ADPCM 等），声道 1/2/3/4/6，采样率 8k–96k。

`fuzz/harness_decode.c` 输出 SF_INFO 头 + 全部 float32 样本（原始小端）+ 尾部计数。
`fuzz/run_compare.py` 对每个文件同时跑 ASan 与参考构建，逐字节比较三段：
元数据头、每一个解码样本、帧数/错误/访问偏移尾部。

## 2. 测试结果

### 2.1 畸形输入（合计 3025 个）

| 指标 | 结果 |
| --- | --- |
| 进程崩溃（信号/非零退出） | **0** |
| AddressSanitizer 堆/栈越界 | **0** |
| UndefinedBehaviorSanitizer 命中 | **0** |
| LeakSanitizer 泄漏 | **0** |
| 无 JSON 输出 / 超时（30s 上限） | 0 |
| 失败缺偏移的记录 | 0 |
| `max_access > size`（潜在越界读） | **0** |

处理结果分布：`open_error` 1895，成功打开并安全解码 `ok` 1130（变异未破坏可解析性的样本，
读取器正常容错读取），无中途 `read_error`。`max_access` 范围 0–92598，中位数 44，
全部落在缓冲区内。失败归并为 **20 种明确错误签名**，每个都带偏移，例如
`Channel count is zero.`、`Malformed 'fmt ' chunk.`、`No 'data' chunk marker.`、
`Supported file format but file is malformed.` 等。

### 2.2 合法输入等价性（500 个）

| 指标 | 结果 |
| --- | --- |
| 元数据头一致 | 500 / 500 |
| 解码样本逐字节一致 | 500 / 500 |
| 尾部（帧数/错误/偏移）一致 | 500 / 500 |
| 比对 float 样本总数 | **2,615,405**，差异 0 |
| ASan 构建非零退出（含泄漏） | 0 |

## 3. 最小反例

`fuzz/minimize.py` 用块删除 delta-debug + 单字节删除 + 字节值收缩，在保持错误签名不变的
前提下最小化；产物在 `fuzz/minis/`，并经 ASan 构建复核为干净退出。精选 14 个：

| 文件 | 原始→最小(字节) | 失败偏移 | 错误签名 |
| --- | --- | --- | --- |
| `00_format_not_recognised.bin` | 0→0 | 0 | Format not recognised. |
| `01_..._no_data_chunk_marker.bin` | 12→12 | 12 | WAV: No 'data' chunk marker. |
| `02_..._unimplemented_format.bin` | 12→12 | 12 | Unimplemented format. |
| `03_channel_count_is_zero.bin` | 12→12 | 12 | Channel count is zero. |
| `04_too_many_channels_specified.bin` | 12→12 | 12 | Too many channels specified. |
| `05_w64_no_data_chunk_marker.bin` | 12→12 | 12 | W64: No 'data' chunk marker. |
| `06_..._file_is_malformed.bin` | 12→12 | 12 | Supported format but malformed. |
| `07_8svx_no_sound_data.bin` | 12→12 | 12 | 8SVX/16SV: no sound data. |
| `08_sfinfo_struct_incomplete.bin` | 60→41 | 41 | SF_INFO struct incomplete. |
| `09_short_fmt_chunk.bin` | 60→20 | 20 | Short 'fmt ' chunk. |
| `10_malformed_fmt_chunk.bin` | 60→17 | 17 | Malformed 'fmt ' chunk. |
| `11_adpcm_invalid_bit_width.bin` | 75→66 | 66 | ADPCM WAV: Invalid bit width. |
| `12_unspecified_internal_error.bin` | 772→16 | 16 | Unspecified internal error. |
| `13_nist_bad_header.bin` | 1172→12 | 12 | NIST: bad header. |

字节级示例（最小 WAV，17 字节，`RIFF…WAVE` 后 `fmt ` 块大小字段被截断，偏移 17 处拒绝）：

```
524946461a00000057415645666d74201f
 RIFF  size=26  WAVE  fmt  (size 字段不完整)
```

每个反例旁有同名 `.json`，记录来源、原始/最小尺寸、错误签名、ASan 复核结果与完整 hex。

## 4. 产物与复现

代码与脚本（均在 `fuzz/`）：

- `vio_track.h`：带偏移追踪与边界钳制的虚拟 IO
- `harness_malformed.c` / `harness_decode.c`：两个测试驱动
- `gen_valid.py` / `gen_malformed.py` / `gen_edge.py`：三类语料生成器
- `run_malformed.py` / `run_compare.py`：批量执行与聚合
- `minimize.py` / `minimize_set.py`：反例最小化
- 报告数据：`report_malformed.json`、`report_edge.json`、`report_compare.json`、
  `minis/counterexamples.json`

一键复现：

```sh
# 1. 两个构建（见下 CMake 配置）
cmake -S . -B build-asan -DCMAKE_BUILD_TYPE=Debug -DBUILD_SHARED_LIBS=OFF \
  -DBUILD_TESTING=OFF -DBUILD_PROGRAMS=OFF -DBUILD_EXAMPLES=OFF \
  -DCMAKE_C_FLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer -g -O1" \
  -DCMAKE_CXX_FLAGS="-fsanitize=address,undefined -fno-omit-frame-pointer -g -O1" \
  -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address,undefined"
cmake --build build-asan -j
cmake -S . -B build-ref -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
  -DBUILD_TESTING=OFF -DBUILD_PROGRAMS=ON
cmake --build build-ref -j

# 2. 编译 harness（链接系统 codec 库：-lm -lpthread -ldl）
# 3. 生成语料
python3 fuzz/gen_valid.py   fuzz/valid 500
python3 fuzz/gen_malformed.py fuzz/valid fuzz/malformed 3000
python3 fuzz/gen_edge.py    fuzz/edge

# 4. 畸形健壮性（ASan/UBSan/LSan）
python3 fuzz/run_malformed.py fuzz/malformed_asan fuzz/malformed fuzz/report_malformed.json
python3 fuzz/run_malformed.py fuzz/malformed_asan fuzz/edge      fuzz/report_edge.json

# 5. 合法文件跨构建逐样本比对
python3 fuzz/run_compare.py fuzz/decode_asan fuzz/decode_ref fuzz/valid fuzz/report_compare.json

# 6. 最小反例
python3 fuzz/minimize_set.py fuzz/malformed_ref fuzz/malformed_asan \
  fuzz/report_malformed.json fuzz/minis 14
```

## 5. 范围说明

- 检测能力来自编译期插桩（ASan/UBSan/LSan），覆盖堆/栈缓冲区越界、use-after-free、
未初始化外的 UB、内存泄漏；不替代长时间覆盖率引导 fuzz（如 libFuzzer）发现深层逻辑缺陷。
- 合法语料由 libsndfile 自身写出，等价性基线是同源码的独立 Release 构建，而非第三方解码器；
这验证的是“被测构建与参考构建行为一致”，不是跨厂商格式兼容性。
- 环境无 clang/valgrind，故未使用 libFuzzer 与 Memcheck；GCC  sanitizer 已覆盖本次目标所需的
崩溃/越界/泄漏三类属性。
