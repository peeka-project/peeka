# Peeka GitHub Pages

This directory contains the GitHub Pages site for the Peeka project.

## Structure

```
gh-pages/
├── _config.yml          # Jekyll configuration
├── index.md             # Landing page (Chinese)
├── installation.md      # Installation guide (Chinese)
├── quickstart.md        # Quick start guide (Chinese)
├── examples.md          # Usage examples (Chinese)
├── architecture.md      # Architecture documentation (Chinese)
├── troubleshooting.md   # Troubleshooting guide (Chinese)
├── commands/            # Command reference pages (Chinese)
│   ├── index.md         # Commands overview
│   ├── attach.md        # attach command
│   ├── watch.md         # watch command
│   ├── trace.md         # trace command
│   ├── stack.md         # stack command
│   ├── monitor.md       # monitor command
│   ├── logger.md        # logger command
│   ├── memory.md        # memory command
│   ├── inspect.md       # inspect command
│   ├── search.md        # search command (sc/sm)
│   └── reset.md         # reset command
└── en/                  # English version
    ├── index.md         # Landing page (English)
    └── commands/        # Command reference (English)
        └── index.md     # Commands overview
```

## Languages

The site supports bilingual documentation:

- **Chinese (中文)**: Root directory - Complete documentation
- **English**: `/en/` directory - Basic structure with home page and commands overview

Users can switch languages using the language selector in the top navigation bar.

### Translation Status

**Chinese**: ✅ Complete
- All main pages
- Complete command documentation (watch, trace, stack, monitor, logger, memory, inspect, search, reset)

**English**: ⏳ In Progress
- ✅ Home page
- ✅ Commands overview
- ⏳ Individual command documentation (planned)
- ⏳ Other guides (installation, quickstart, etc.)

## Theme

This site uses the [Just the Docs](https://just-the-docs.github.io/just-the-docs/) theme, which provides:

- Clean, professional documentation layout
- Built-in search functionality
- Mobile-responsive design
- Easy navigation structure
- Code syntax highlighting

## Local Development

### Prerequisites

- Ruby 3.1+
- Bundler

### Setup

```bash
cd gh-pages

# Install dependencies
bundle install

# Run local server
bundle exec jekyll serve --baseurl "/peeka"

# Open browser to http://localhost:4000/peeka
```

### Build

```bash
bundle exec jekyll build --baseurl "/peeka"
```

The built site will be in `_site/`.

## Deployment

The site is automatically deployed via GitHub Actions when changes are pushed to the `main` branch.

See `.github/workflows/deploy-pages.yml` for the deployment configuration.

## GitHub Pages Settings

To enable GitHub Pages for this repository:

1. Go to repository Settings → Pages
2. Source: GitHub Actions
3. The site will be available at `https://wwulfric.github.io/peeka`

## Adding New Pages

1. Create a new `.md` file in the `gh-pages/` directory
2. Add front matter:
   ```yaml
   ---
   layout: default
   title: Your Page Title
   nav_order: 10
   ---
   ```
3. Write your content in Markdown
4. The page will automatically appear in the navigation

## Adding New Command Documentation

1. Create a new `.md` file in `gh-pages/commands/`
2. Add front matter:
   ```yaml
   ---
   layout: default
   title: command-name
   parent: 命令参考
   nav_order: X
   ---
   ```
3. Document the command

## Navigation Order

Pages are sorted by `nav_order` in the front matter:

- 1: 首页 (Home)
- 2: 安装指南 (Installation)
- 3: 快速开始 (Quick Start)
- 4: 命令参考 (Commands)
- 5: 示例教程 (Examples)
- 8: 架构设计 (Architecture)
- 9: 故障排除 (Troubleshooting)

## Updating Documentation

When the project documentation changes:

1. Update the corresponding `.md` files in `gh-pages/`
2. Commit and push to `main`
3. GitHub Actions will automatically rebuild and deploy the site

## Customization

### Colors

Edit `_config.yml` to change the color scheme:

```yaml
color_scheme: light  # or dark, nil (system)
```

### Logo

Add a logo by placing an image in `assets/images/` and updating `_config.yml`:

```yaml
logo: "/assets/images/logo.png"
```

### Footer

Edit the footer content in `_config.yml`:

```yaml
footer_content: "Your custom footer text"
```

## Resources

- [Just the Docs Documentation](https://just-the-docs.github.io/just-the-docs/)
- [Jekyll Documentation](https://jekyllrb.com/docs/)
- [GitHub Pages Documentation](https://docs.github.com/en/pages)
