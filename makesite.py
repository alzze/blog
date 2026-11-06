#!/usr/bin/env python3
import os
from datetime import datetime
import shutil
from pathlib import Path
import markdown
from jinja2 import Environment, FileSystemLoader


def create_directory(dir):
    dir = 'dist/' + dir
    if os.path.exists(dir):
        shutil.rmtree(dir)
    os.makedirs(dir, exist_ok=True)


def get_posts(source='posts', url_prefix='/posts/'):
    result = []
    posts = list(Path(source).glob('*.md'))
    for post in posts:
        slug, _ = os.path.splitext(post.name)
        url = url_prefix + slug + '/'
        with open(post, "r", encoding="utf-8") as f:  
            lines = f.readlines()
        if lines[0].strip() == "---":
            frontmatter_end = None
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    frontmatter_end = i
                    break
            if frontmatter_end:
                p = {}
                p['url'] = url
                p['slug'] = slug
                for line in lines[1:frontmatter_end]:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        p[key.strip()] = value.strip().strip('"')
                if 'date' in p:
                    p['_date'] = datetime.strptime(p['date'], '%Y-%m-%d')
                else:
                    p['_date'] = datetime.min
                markdown_content = "".join(lines[frontmatter_end + 1:]).strip()
                p['content'] = markdown.markdown(markdown_content, extensions=['tables', 'fenced_code'])
                if p.get('draft', '').lower() != 'true':
                    result.append(p)
    result.sort(key=lambda p: p['_date'], reverse=True)
    return result


def render_file(template, out_file, context=None):
    if context is None:
        context = {}
    template_dir = os.path.dirname(template)
    template_name = os.path.basename(template)
    env = Environment(
        loader=FileSystemLoader(template_dir),
    )
    tmpl = env.get_template(template_name)
    rendered_content = tmpl.render(context)
    os.makedirs('dist', exist_ok=True)
    out_path = os.path.join('dist', out_file)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(rendered_content)


def generate_posts(posts, base_dir='posts'):
    create_directory(base_dir)
    for post in posts:
        rel_path = post["url"].strip('/')
        create_directory(rel_path)
        render_file('templates/post.html', rel_path + '/index.html', {'post': post})


if __name__ == '__main__':
    en_posts = get_posts('posts', '/posts/')
    es_posts = get_posts('posts/es', '/es/posts/')

    create_directory('')
    shutil.copytree('static', 'dist', dirs_exist_ok=True)

    generate_posts(en_posts, 'posts')
    
    render_file('templates/index.html', 'index.html', {'posts': en_posts, 'lang': 'en'})