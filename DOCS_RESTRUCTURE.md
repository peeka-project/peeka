# 文档重构说明 / Documentation Restructuring Notes

## 概述 / Overview

本次更新完成了 Peeka 项目文档的重组和双语支持。

This update completes the reorganization and bilingual support for Peeka project documentation.

## 主要变更 / Main Changes

### 1. 命令文档整合 / Command Documentation Integration

**变更 / Change:**
- 将 `/docs` 目录下的所有命令文档（watch.md, trace.md, stack.md, monitor.md, logger.md, memory.md, inspect.md, search.md, reset.md）移动到 `gh-pages/commands/` 目录
- Moved all command documentation from `/docs` directory to `gh-pages/commands/`

**详情 / Details:**
- 为每个文档添加了 Jekyll frontmatter（layout, title, parent, nav_order）
- Added Jekyll frontmatter to each document (layout, title, parent, nav_order)
- 更新了 `gh-pages/commands/index.md` 以包含所有命令的链接
- Updated `gh-pages/commands/index.md` to include links to all commands

**文件列表 / File List:**
```
gh-pages/commands/
├── index.md        # 命令概览 / Commands overview
├── attach.md       # 附加进程 / Attach to process
├── watch.md        # 观测函数 / Watch functions
├── trace.md        # 追踪调用链 / Trace call chain
├── stack.md        # 追踪调用栈 / Trace call stack
├── monitor.md      # 性能监控 / Performance monitoring
├── logger.md       # 日志管理 / Log management
├── memory.md       # 内存分析 / Memory analysis
├── inspect.md      # 对象检查 / Object inspection
├── search.md       # 搜索类和方法 / Search classes and methods
└── reset.md        # 重置增强 / Reset enhancements
```

### 2. 双语支持 / Bilingual Support

**变更 / Change:**
- 在 `gh-pages/_config.yml` 中添加语言切换链接
- Added language switcher links in `gh-pages/_config.yml`
- 创建英文版本目录结构 `gh-pages/en/`
- Created English version directory structure `gh-pages/en/`

**配置更新 / Configuration Updates:**
```yaml
aux_links:
  "English":
    - "/peeka/en/"
  "中文":
    - "/peeka/"
  "Peeka on GitHub":
    - "https://github.com/wwulfric/peeka"
```

### 3. 英文版本内容 / English Version Content

**创建的文件 / Created Files:**
```
gh-pages/en/
├── index.md              # 英文主页 / English home page
├── commands/
│   └── index.md          # 英文命令概览 / English commands overview
└── README.md             # 英文版说明 / English version notes
```

**翻译状态 / Translation Status:**
- ✅ 主页 (Home page)
- ✅ 命令概览 (Commands overview)
- ⏳ 各命令详细文档（计划中）/ Individual command docs (planned)
- ⏳ 其他指南页面（计划中）/ Other guide pages (planned)

### 4. 语言提示 / Language Notes

在中文和英文主页都添加了语言切换提示：
Added language switcher notes on both Chinese and English home pages:

```markdown
{: .note }
> 🌐 **Language / 语言**: This documentation is also available in [English](/peeka/en/).
>
> 本文档也提供[英文版本](/peeka/)。
```

## 目录结构 / Directory Structure

```
gh-pages/
├── _config.yml                    # Jekyll 配置（含语言切换）
├── index.md                       # 中文主页
├── installation.md                # 安装指南（中文）
├── quickstart.md                  # 快速开始（中文）
├── examples.md                    # 示例（中文）
├── architecture.md                # 架构设计（中文）
├── comparison.md                  # 与 Arthas 对比（中文）
├── troubleshooting.md             # 故障排除（中文）
├── commands/                      # 命令文档（中文）- 完整
│   ├── index.md
│   ├── attach.md
│   ├── watch.md
│   ├── trace.md
│   ├── stack.md
│   ├── monitor.md
│   ├── logger.md
│   ├── memory.md
│   ├── inspect.md
│   ├── search.md
│   └── reset.md
└── en/                            # 英文版本
    ├── index.md                   # 英文主页
    ├── commands/                  # 命令文档（英文）- 基础结构
    │   └── index.md
    └── README.md                  # 说明文档
```

## 用户体验 / User Experience

### 语言切换 / Language Switching

用户可以通过以下方式切换语言：
Users can switch languages through:

1. **顶部导航栏 / Top navigation bar**: 点击 "English" 或 "中文" 链接
2. **页面提示 / Page notes**: 主页顶部的语言切换提示
3. **直接访问 / Direct access**:
   - 中文：`https://wwulfric.github.io/peeka/`
   - English: `https://wwulfric.github.io/peeka/en/`

### 搜索功能 / Search Functionality

Just the Docs 主题的搜索功能会索引所有语言的内容。
The Just the Docs theme's search will index content in all languages.

## 后续工作 / Future Work

### 高优先级 / High Priority
1. 翻译各个命令的详细文档到英文
   Translate detailed command documentation to English
2. 翻译安装指南到英文
   Translate installation guide to English
3. 翻译快速开始指南到英文
   Translate quickstart guide to English

### 中优先级 / Medium Priority
4. 翻译架构文档到英文
   Translate architecture documentation to English
5. 翻译示例教程到英文
   Translate examples to English
6. 翻译故障排除指南到英文
   Translate troubleshooting guide to English

### 低优先级 / Low Priority
7. 考虑使用 Jekyll 插件实现更高级的多语言支持
   Consider using Jekyll plugins for advanced multilingual support
8. 添加语言选择器组件到每个页面
   Add language selector component to each page

## 技术细节 / Technical Details

### Jekyll 配置 / Jekyll Configuration

- 使用 Just the Docs 主题
  Using Just the Docs theme
- 通过 `aux_links` 实现语言切换
  Language switching implemented via `aux_links`
- 英文页面使用 `/en/` 路径前缀
  English pages use `/en/` path prefix

### 前置事项 (Frontmatter) 格式 / Frontmatter Format

**中文页面 / Chinese Pages:**
```yaml
---
layout: default
title: watch 命令
parent: 命令参考
nav_order: 2
---
```

**英文页面 / English Pages:**
```yaml
---
layout: default
title: Command Reference
nav_order: 4
has_children: true
permalink: /en/commands
---
```

## 测试清单 / Testing Checklist

部署后需要验证 / Verify after deployment:

- [ ] 中文主页正常显示 / Chinese home page displays correctly
- [ ] 英文主页正常显示 / English home page displays correctly
- [ ] 所有命令文档链接可访问 / All command documentation links accessible
- [ ] 语言切换链接工作正常 / Language switcher links work
- [ ] 搜索功能正常 / Search functionality works
- [ ] 移动端显示正常 / Mobile display correct
- [ ] 代码高亮正常 / Code highlighting works

## 兼容性 / Compatibility

- Jekyll 4.x+
- Just the Docs 主题 / theme
- GitHub Pages 兼容 / GitHub Pages compatible

## 相关文件 / Related Files

- `GITHUB_PAGES_SETUP.md` - GitHub Pages 设置指南
- `gh-pages/README.md` - gh-pages 目录说明
- `gh-pages/en/README.md` - 英文版本说明

---

**更新日期 / Last Updated:** 2025-02-12
**作者 / Author:** Claude (Anthropic)
