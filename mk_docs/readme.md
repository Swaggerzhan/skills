# AI 文档渲染服务（MkDocs Material）

AI 产出的 md 写入 `${DEPLOY_PATH}`，浏览器实时渲染，落盘自动刷新。

## 0. 定部署路径

后续所有命令都依赖这个变量，先定义（每个新 shell 都要重新 export）：

```bash
export DEPLOY_PATH=/path/to/docs
```

`mkdocs.yml` 通过 `!ENV` 读取它，启动前未设置会直接报错。

以下命令均以本仓库根目录（`mk_docs/` 所在目录）为工作目录。

## 1. 安装

```bash
pip install mkdocs-material
```

## 2. 部署辅助文件

yml 里引用了两个本地文件，路径固定如下（相对于 docs 根目录）：

```bash
mkdir -p ${DEPLOY_PATH}/javascripts
cp mk_docs/js/extra.css  ${DEPLOY_PATH}/extra.css
cp mk_docs/js/katex.js   ${DEPLOY_PATH}/javascripts/katex.js
```

- `extra.css`：解开表格限宽
- `javascripts/katex.js`：数学公式渲染

不需要的功能可以不拷贝，但要同步删掉 `mkdocs.yml` 里 `extra_css` / `extra_javascript` 中对应的本地文件引用，否则启动报错。

## 3. 启动

前台（推荐，tmux 里跑）：

```bash
mkdocs serve -f mk_docs/mkdocs.yml -a 0.0.0.0:8000
```

后台：

```bash
nohup mkdocs serve -f mk_docs/mkdocs.yml -a 0.0.0.0:8000 >/tmp/mkdocs.log 2>&1 &
```

浏览器访问 `http://<服务器IP>:8000`。

## 4. 结束

前台：`Ctrl+C`。后台：`pkill -f mk_docs/mkdocs.yml`。

## 注意

- mermaid 图表和 KaTeX 公式依赖 unpkg.com CDN，**浏览器端**需能访问；CDN 不可达时仅公式/图表不渲染，正文、表格、搜索不受影响。
- AI 侧约定：文档一律写到 `${DEPLOY_PATH}` 下（可建子目录，导航自动按文件树生成）；插图需一并放入该目录并用相对路径引用。
