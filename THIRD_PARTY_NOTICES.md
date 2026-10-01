# 第三方组件与许可说明

本项目原创程序代码适用根目录 LICENSE 中的 AGPL-3.0-only。以下组件的版权与许可由各自权利人保留，不因本项目发布而变更。有关详细条件以随附许可文本为准。

| 组件 | 版本 | 许可 |
| --- | --- | --- |
| PyMuPDF | 1.26.7 | GNU AGPL v3；上游另提供商业许可 |
| MuPDF（PyMuPDF 内嵌引擎） | 1.26.12 | GNU AGPL v3；内部第三方组件保留其许可 |
| CPython | 3.12.14 | PSF 许可及随附第三方许可 |
| Tcl / Tk | 8.6.12 | licenses 内所附许可 |
| PyInstaller | 6.22.3 | GPL v2-or-later 及随附 bootloader exception；其构建产物受该例外规定 |
| Noto Sans CJK SC 样例字体子集 | 2.004 | SIL Open Font License 1.1 |
| altgraph | 0.17.5 | MIT |
| packaging | 26.3 | BSD-2-Clause / Apache-2.0 |
| pefile | 2024.8.26 | MIT |
| pyinstaller-hooks-contrib | 2026.8 | GPL v2-or-later；详见其许可及例外 |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause |
| setuptools | 84.0.0 | MIT；内置依赖各自许可 |

字体版权：© 2014–2021 Adobe (http://www.adobe.com/)。仓库中的 sample-subset.ttf 是用于虚构测试 PDF 的字体子集，OFL 全文见 licenses/Noto-Sans-CJK-OFL.txt。样例 PDF 嵌入字体。界面使用 Windows 已安装的字体，本项目不分发 Microsoft 字体。

PyMuPDF 和 MuPDF 的相应源码分别随公开 Release 包的 third-party-sources/pymupdf-1.26.7.tar.gz 和 mupdf-1.26.12-source.tar.gz 提供。MuPDF 上游源码包保留内部第三方源码与许可。根目录 LICENSE 提供完整 AGPL 文本。

该源码包 SHA-256：71add8bdc8eb1aaa207c69a13400693f06ad9b927bea976f5d5ab9df0bb489c3。

上游来源：

- [PyMuPDF 1.26.7](https://pypi.org/project/PyMuPDF/1.26.7/#files)
- [MuPDF](https://mupdf.com/)
- [CPython 3.12.14 源码](https://github.com/python/cpython/tree/v3.12.14)
- [Tcl 8.6.12 源码](https://github.com/tcltk/tcl/tree/core-8-6-12)
- [Tk 8.6.12 源码](https://github.com/tcltk/tk/tree/core-8-6-12)
- [PyInstaller](https://github.com/pyinstaller/pyinstaller)
- [Noto CJK 字体许可](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE)

其他实际随附许可见 licenses/third-party；离线依赖 wheel 也保留各自的 dist-info 许可文件。原有许可短说明与完整上游文本应一并阅读。分发修改版时请同时更新对应源码、版本说明和组件许可。
