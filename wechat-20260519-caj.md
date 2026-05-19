GangDan现在能直接上传CAJ了——知网论文一键入库

GangDan 是个开源的 RAG 知识库工具，支持下载 arXiv 论文、上传各种文档、自动转 Markdown 建库。项目地址：https://github.com/cycleuser/GangDan

之前有人问能不能传知网的 CAJ 文件。CAJ 是中国知网的专有格式，拿普通 PDF 工具根本打不开，更别说往知识库里放了。每次都得先在知网在线看，手动复制粘贴，费时费力还容易丢格式。

这回加上了 CAJ 支持。上传 `.caj` 文件后，后台自动走 CAJ→PDF→Markdown 的转换管线：先用 caj2pdf 把 CAJ 转成 PDF，再用 GangDan 已有的 docling/pymupdf 引擎把 PDF 转成 Markdown。拿一篇内蒙扎兰屯的铅锌银铜矿床地质论文试了，998KB 的 CAJ 文件，十几秒出结果，标题、作者、正文都提取出来了。

关键的一点：转换的中间态 PDF 会和 CAJ 原件、Markdown 一块留在知识库目录里。导出知识库时三样都打包，不会只给你一个 Markdown 丢掉原始文件。之前 PDF 上传也是一样，原件和转出来的 Markdown 都在。

顺手还把知识库的语言选择扩充了。原来只有中英日三个选项，现在加了韩语、法语、德语、西语、葡语、俄语、意大利语，一共十个。还多了个「Auto」选项，勾上之后自动从文档内容检测语言——中文文档识别出中文，英文文档识别出英文，不用手动选。Auto 和具体语言互斥，点 Auto 其他选项清空，选具体语言 Auto 就取消。

这次还修了个 ChromaDB 文档去重的 bug：上传类的知识库 chunk 里只有 file 字段没有 doc_id，41 个 chunk 在列表里显示成 41 篇"文章"，现在正确合并成 1 篇了。

CAJ 支持依赖 caj2pdf-restructured 这个库，pip install caj2pdf-restructured 就行。没装的话不影响其他功能，上传 PDF、Markdown 什么的照常用。不过 caj2pdf 对 HN 格式的支持还不太稳，CAJ 和 KDH 格式一般没问题。

---

技术细节：CAJConverter 在 pdf_converter.py 里，继承 PDFConverter 的引擎优先链（docling > pymupdf > pdfplumber > basic），CAJ 源文件经 caj2pdf 解析后先生成临时 PDF，shutil.copy2 保存到 KB 目录，再走 PDF 转换管线。语言检测用 Unicode 字符范围：CJK 区间判中文，平假名/片假名判日文，韩文判韩语，西里尔判俄语，其余判英文，不需要额外依赖。