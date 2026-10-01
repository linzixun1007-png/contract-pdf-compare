> 发布状态：项目源码已公开；测试 PDF 与包含它们的免安装包正在等待附件公开授权，暂未上传。内置验收需要这些样例，当前请先查看源码和部署说明。

# 合同 PDF 对比工具 / Contract PDF Compare

一个在本地运行的中文合同 PDF 文字核对工具。选择基准版、待校验版和比较档位，生成可以复核的 HTML 差异报告。不调用大模型，不上传合同，不包含 OCR。

## 下载与打开

到 [Releases](https://github.com/linzixun1007-png/contract-pdf-compare/releases) 下载公开发布包，先完整解压。

- 单文件免安装：打开 01_单文件免安装里的 合同PDF对比.exe。
- 文件夹免安装：打开 02_文件夹免安装/合同PDF对比 里的同名程序；保留旁边的 _internal 文件夹。
- IT 部署：03_源码与IT部署 提供源码和可指定目录的离线安装、构建脚本；04_离线依赖 是 Windows x64 离线依赖。

免安装版面向 Windows x64，无需安装 Python。机构内使用请按所在单位的 IT 管理要求部署。仓库只存源码、虚构样例和许可文件，大文件随 Release 分发。

## 一个程序，三个比较档位

| 档位 | 适用场景 |
| --- | --- |
| 严格复核（默认） | 保留较多字符差异；水印需要明确医院名及位置/旋转特征 |
| 常规合同 | 放宽空格和兼容字符差异，并允许符合规则的医院水印 |
| 宽松排版 | 进一步放宽水印位置和重复水印判断；结果应更仔细复核 |

详见 [比较档位说明](docs/比较档位说明.md)。报告记录程序版本、档位、文件摘要和比较范围。

扫描页、文字解码异常等情况会提示无法完整比较，不能据此认定合同一致。结果只覆盖可提取的文字及所识别的表格内容；图像、印章、签名和视觉排版需要人工检查。水印判断是启发式规则，宽松设置可能忽略有意义的文字。

## 从源码运行

建议使用 Python 3.12，在 Windows x64 上执行：

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-runtime.txt
.\.venv\Scripts\python.exe gui.py
~~~

命令行参数见 python compare.py --help 和 python batch_compare.py --help。
compare.py 返回码：0 为可比较且一致，1 为执行/保存失败，2 为存在差异，3 为无法完整比较。
固定依赖及离线包面向 Windows x64；其他平台需自行选择兼容 PyMuPDF 版本并验证。

## 验证与重建

~~~powershell
python self_test.py
python gui.py --gui-check --result gui-check.json
python -m pip install --require-hashes -r requirements-build.txt
python build_exe.py --mode both --output build
~~~

内置验收有 62 项检查和 37 份虚构 PDF。测试覆盖已知场景，不是准确率承诺。原始样例中 4 个文字映射异常场景预期为“无法完整比较”；详情见 [测试说明](docs/测试说明.md)。
两种 exe 使用同一份源码和比较逻辑。详见 [构建与部署](docs/构建与部署.md)。

## 开源许可

本项目代码使用 [GNU AGPL-3.0-only](LICENSE)。允许在其条件下使用、修改、分发；分发程序时须提供相应源码及许可，修改版用于网络交互时也有对应源码义务。
第三方组件保留各自许可，见 [第三方说明](THIRD_PARTY_NOTICES.md)。本工具不提供担保。
提交问题或样例时，请使用虚构/脱敏文件，勿上传真实合同、个人资料或单位机密。

Offline Chinese contract PDF text comparison with three selectable profiles, conservative watermark filtering and auditable HTML reports. No cloud upload, LLM or OCR. Scanned or undecodable pages are reported as inconclusive. Windows x64 portable builds, offline dependencies and build instructions are distributed in Releases. Licensed under AGPL-3.0-only; third-party components retain their own licenses.
