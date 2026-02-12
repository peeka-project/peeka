# GitHub Pages 设置指南

这个 PR 为 Peeka 项目添加了完整的 GitHub Pages 文档网站。

## 📋 已完成的工作

### 1. 网站结构

创建了 `gh-pages/` 目录，包含：

#### 中文文档（完整）

- **首页** (`index.md`) - 项目概览、核心特性、快速开始
- **安装指南** (`installation.md`) - 各平台安装说明、权限配置
- **快速开始** (`quickstart.md`) - 基础使用教程、数据处理示例
- **命令参考** (`commands/`) - 完整的命令文档
  - `index.md` - 命令概览
  - `attach.md` - attach 命令
  - `watch.md` - watch 命令
  - `trace.md` - trace 命令
  - `stack.md` - stack 命令
  - `monitor.md` - monitor 命令
  - `logger.md` - logger 命令
  - `memory.md` - memory 命令
  - `inspect.md` - inspect 命令
  - `search.md` - search 命令 (sc/sm)
  - `reset.md` - reset 命令
- **示例教程** (`examples.md`) - 7 个实际应用场景
- **与 Arthas 对比** (`comparison.md`) - 功能对比、性能分析
- **架构设计** (`architecture.md`) - 设计理念、核心组件
- **故障排除** (`troubleshooting.md`) - 常见问题解决方案

#### 英文文档（基础结构）

- **首页** (`en/index.md`) - 项目介绍、核心特性、快速开始
- **命令参考** (`en/commands/index.md`) - 命令概览

### 2. 双语支持

- **语言切换器** - 在顶部导航栏添加中英文切换链接
- **语言提示** - 在主页添加语言切换提示
- **独立目录** - 英文文档位于 `/en/` 路径下
- **灵活扩展** - 可按需添加更多语言版本

### 3. GitHub Actions 工作流

创建了 `.github/workflows/deploy-pages.yml`，实现：

- 自动构建 Jekyll 网站
- 自动部署到 GitHub Pages
- 当 `gh-pages/` 目录或工作流文件更新时触发

### 4. Jekyll 配置

- 使用 **Just the Docs** 主题 - 专业的文档网站模板
- 配置了搜索功能
- 中英文混合支持
- 移动端响应式设计

## 🚀 启用 GitHub Pages

### 方法 1: GitHub Actions（推荐）

1. 进入仓库 **Settings** → **Pages**
2. **Source** 选择：**GitHub Actions**
3. 合并这个 PR 后，网站会自动部署

### 方法 2: 从分支部署

1. 进入仓库 **Settings** → **Pages**
2. **Source** 选择：**Deploy from a branch**
3. **Branch** 选择：`main` + `/gh-pages` 文件夹
4. 保存后自动部署

### 访问网站

部署完成后，网站将在以下地址访问：

```
https://wwulfric.github.io/peeka
```

## 📝 本地预览

### 安装依赖

```bash
cd gh-pages

# 安装 Ruby 依赖
bundle install
```

### 运行本地服务器

```bash
bundle exec jekyll serve --baseurl "/peeka"
```

然后访问：`http://localhost:4000/peeka`

### 构建网站

```bash
bundle exec jekyll build --baseurl "/peeka"
```

生成的网站在 `gh-pages/_site/` 目录。

## 🔧 自定义配置

### 修改主题颜色

编辑 `gh-pages/_config.yml`:

```yaml
color_scheme: light  # 可选: light, dark, nil (跟随系统)
```

### 添加 Logo

1. 将 logo 图片放在 `gh-pages/assets/images/logo.png`
2. 在 `_config.yml` 中取消注释：
   ```yaml
   logo: "/assets/images/logo.png"
   ```

### 修改页脚

编辑 `gh-pages/_config.yml` 中的 `footer_content`。

### 添加 Google Analytics

在 `_config.yml` 中添加：

```yaml
ga_tracking: UA-XXXXXXXXX-X
```

## 📄 添加新页面

### 创建普通页面

1. 在 `gh-pages/` 目录创建新的 `.md` 文件
2. 添加 front matter：
   ```yaml
   ---
   layout: default
   title: 页面标题
   nav_order: 10
   ---
   ```
3. 写入内容

### 添加命令文档

1. 在 `gh-pages/commands/` 创建新文件，如 `watch.md`
2. 添加 front matter：
   ```yaml
   ---
   layout: default
   title: watch
   parent: 命令参考
   nav_order: 2
   ---
   ```
3. 按照 `attach.md` 的格式编写文档

## 🌐 网站特性

### 搜索功能

网站内置全文搜索，用户可以快速找到需要的内容。

### 响应式设计

支持桌面、平板、移动设备自适应显示。

### 代码高亮

支持 Python、Bash、JSON 等多种语言的语法高亮。

### SEO 优化

使用 jekyll-seo-tag 插件，优化搜索引擎收录。

## 📚 待完善内容

目前网站已包含核心内容，以下是可选的扩展：

1. ~~**命令文档补全**~~：✅ 已完成 - 所有命令文档已添加
   - ✅ watch.md
   - ✅ trace.md
   - ✅ stack.md
   - ✅ monitor.md
   - ✅ logger.md
   - ✅ memory.md
   - ✅ inspect.md
   - ✅ search.md (sc/sm)
   - ✅ reset.md

2. **英文文档翻译**：⏳ 已完成基础结构
   - ✅ 英文主页
   - ✅ 命令概览
   - ⏳ 各命令详细文档（待翻译）
   - ⏳ 安装指南（待翻译）
   - ⏳ 快速开始（待翻译）
   - ⏳ 架构设计（待翻译）
   - ⏳ 其他指南（待翻译）

3. **视觉元素**：
   - 添加项目 Logo
   - 添加示例截图
   - 添加架构图表

4. **视频教程**：
   - 可选：录制使用演示视频

5. **API 文档**：
   - 可选：使用 Sphinx 生成 Python API 文档

## ✅ 检查清单

在启用 GitHub Pages 前，请确认：

- [ ] 仓库设置中启用了 GitHub Pages
- [ ] 工作流有必要的权限（Settings → Actions → General → Workflow permissions: Read and write）
- [ ] 合并 PR 到 main 分支
- [ ] 等待 GitHub Actions 完成部署（约 2-3 分钟）
- [ ] 访问网站确认正常显示

## 🔗 相关资源

- [Just the Docs 主题文档](https://just-the-docs.github.io/just-the-docs/)
- [Jekyll 文档](https://jekyllrb.com/docs/)
- [GitHub Pages 文档](https://docs.github.com/en/pages)
- [Jekyll SEO Tag](https://github.com/jekyll/jekyll-seo-tag)

## 💡 提示

1. **首次部署**：GitHub Actions 首次运行可能需要几分钟
2. **自定义域名**：可在仓库设置中配置自定义域名
3. **HTTPS**：GitHub Pages 自动提供 HTTPS 支持
4. **更新网站**：只需更新 `gh-pages/` 目录中的文件并推送即可

## 🎉 完成！

网站设计专业、内容全面，包含了用户需要的所有信息：

- ✅ 项目介绍和特性展示
- ✅ 完整的安装指南
- ✅ 详细的使用教程
- ✅ 命令参考文档
- ✅ 实际应用场景示例
- ✅ 与同类工具的对比
- ✅ 架构设计说明
- ✅ 故障排除指南

用户可以快速了解 Peeka 并开始使用！
