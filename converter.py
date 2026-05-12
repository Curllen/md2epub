import os
import markdown
import ebooklib
from ebooklib import epub
from pathlib import Path
import re
import mimetypes
from bs4 import BeautifulSoup

class EpubConverter:
    def __init__(self, log_callback=None):
        self.book = None
        self.images_dir = None
        self.log_callback = log_callback if log_callback else lambda msg, level="info": print(msg)
    
    def log(self, message, level="info"):
        """输出日志消息"""
        if self.log_callback:
            self.log_callback(message, level)
    
    def create_book(self, title, author, cover_path=None):
        """创建新的EPUB书籍"""
        self.log(f"正在创建EPUB书籍: {title}")
        self.book = epub.EpubBook()
        self.book.set_title(title)
        self.book.set_language('zh-CN')
        self.book.add_author(author)
        
        if cover_path and os.path.exists(cover_path):
            self.log(f"添加封面图片: {cover_path}")
            self.book.set_cover('cover.jpg', open(cover_path, 'rb').read())
    
    def add_markdown_file(self, md_path, custom_toc=None):
        """添加Markdown文件到EPUB"""
        if not self.book:
            raise ValueError("请先创建书籍")
        
        self.log(f"处理Markdown文件: {md_path}")
        
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        self.log("转换Markdown为HTML...")
        html_content = markdown.markdown(md_content, extensions=['extra', 'toc'])
        
        md_dir = os.path.dirname(md_path)
        html_content = self.process_images(html_content, md_dir)
        
        file_name = os.path.basename(md_path).replace('.md', '')
        chapter = epub.EpubHtml(
            title=str(file_name),
            file_name=f'{file_name}.xhtml'
        )
        chapter.content = html_content
        chapter.original_content = html_content
        chapter.file_path = md_path
        
        self.book.add_item(chapter)
        self.log(f"章节 '{file_name}' 添加完成")
        return chapter
    
    def process_images(self, html_content, md_dir=None):
        """处理HTML中的图片引用"""
        img_pattern = re.compile(r'<img[^>]+src="([^"]+)"[^>]*>')
        
        def replace_img(match):
            img_src = match.group(1)
            
            if img_src.startswith(('http://', 'https://')):
                return match.group(0)
            
            if os.path.isabs(img_src):
                if os.path.exists(img_src):
                    return self.add_image_to_epub(img_src, match.group(0))
                return match.group(0)
            
            if md_dir:
                md_img_path = os.path.normpath(os.path.join(md_dir, img_src))
                if os.path.exists(md_img_path):
                    return self.add_image_to_epub(md_img_path, match.group(0))
            
            if self.images_dir:
                img_path = os.path.normpath(os.path.join(self.images_dir, img_src))
                if os.path.exists(img_path):
                    return self.add_image_to_epub(img_path, match.group(0))
                
                img_filename = os.path.basename(img_src)
                img_path = os.path.normpath(os.path.join(self.images_dir, img_filename))
                if os.path.exists(img_path):
                    return self.add_image_to_epub(img_path, match.group(0))
            
            return match.group(0)
        
        return re.sub(img_pattern, replace_img, html_content)
    
    def add_image_to_epub(self, img_path, img_tag):
        """将图片添加到EPUB"""
        img_name = os.path.basename(img_path)
        try:
            with open(img_path, 'rb') as f:
                img_file = f.read()
                
            img_item = epub.EpubItem(
                uid=img_name.replace('.', '_').replace('-', '_'),
                file_name=f'images/{img_name}',
                media_type=self.get_mimetype(img_path),
                content=img_file
            )
            self.book.add_item(img_item)
            self.log(f"添加图片: {img_name}")
            
            return img_tag.replace(f'src="{img_path}"', f'src="images/{img_name}"').replace(f"src='{img_path}'", f"src='images/{img_name}'")
        except Exception as e:
            self.log(f"添加图片出错: {str(e)}", "warning")
            return img_tag
    
    def get_mimetype(self, file_path):
        """获取文件的MIME类型"""
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            return mime_type
        
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.jpg', '.jpeg'):
            return 'image/jpeg'
        elif ext == '.png':
            return 'image/png'
        elif ext == '.gif':
            return 'image/gif'
        elif ext == '.svg':
            return 'image/svg+xml'
        
        return 'application/octet-stream'
    
    def natural_sort_key(self, s):
        """生成自然排序的键"""
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]
    
    def add_markdown_directory(self, dir_path, custom_toc=None):
        """添加目录中的所有Markdown文件到EPUB"""
        if not self.book:
            raise ValueError("请先创建书籍")
        
        chapters = []
        md_files = sorted([f for f in os.listdir(dir_path) if f.endswith('.md')], key=self.natural_sort_key)
        
        self.log(f"发现 {len(md_files)} 个Markdown文件")
        
        for md_file in md_files:
            md_path = os.path.join(dir_path, md_file)
            chapter = self.add_markdown_file(md_path, custom_toc)
            chapters.append(chapter)
        
        return chapters
    
    def generate_toc(self, chapters, custom_toc=None, toc_type="auto"):
        """生成目录"""
        self.log(f"生成目录 (模式: {toc_type})...")
        
        if custom_toc:
            toc = []
            for item in custom_toc:
                toc.append(epub.Link(item['file'], item['title'], item['id']))
            self.book.toc = toc
        elif toc_type == "filename":
            toc = []
            for chapter in chapters:
                chapter_title = str(chapter.title)
                chapter_filename = chapter.file_name
                link = epub.Link(chapter_filename, chapter_title, chapter_filename.replace('.', '_'))
                toc.append(link)
            self.book.toc = toc
        else:
            toc = []
            
            for chapter in chapters:
                chapter_title = str(chapter.title)
                chapter_filename = chapter.file_name
                
                chapter_link = epub.Link(chapter_filename, chapter_title, chapter_filename.replace('.', '_'))
                
                if not hasattr(chapter, 'original_content'):
                    toc.append(chapter_link)
                    continue
                
                soup = BeautifulSoup(chapter.original_content, 'html.parser')
                headings = soup.find_all(['h1', 'h2', 'h3'])
                
                if not headings:
                    toc.append(chapter_link)
                    continue
                
                h1_sections = {}
                h2_sections = {}
                chapter_items = []
                
                for heading in headings:
                    level = int(heading.name[1])
                    heading_text = str(heading.get_text())
                    heading_id = heading.get('id', '')
                    
                    if not heading_id:
                        heading_id = 'heading_' + re.sub(r'\W+', '_', heading_text.lower())
                    
                    heading_link = f"{chapter_filename}#{heading_id}"
                    link_id = heading_link.replace('.', '_').replace('#', '_')
                    link = epub.Link(heading_link, heading_text, link_id)
                    
                    if level == 1:
                        section = epub.Section(heading_text)
                        h1_sections[heading_text] = {
                            'section': section,
                            'link': link,
                            'items': []
                        }
                        chapter_items.append((section, [link]))
                        current_h1 = heading_text
                    elif level == 2 and current_h1 in h1_sections:
                        section = epub.Section(heading_text)
                        h2_sections[heading_text] = {
                            'section': section,
                            'link': link,
                            'items': [],
                            'parent': current_h1
                        }
                        h1_sections[current_h1]['items'].append((section, [link]))
                        current_h2 = heading_text
                    elif level == 3 and current_h2 in h2_sections:
                        h2_sections[current_h2]['items'].append(link)
                    elif level == 3 and current_h1 in h1_sections:
                        h1_sections[current_h1]['items'].append(link)
                    elif level == 2:
                        section = epub.Section(heading_text)
                        chapter_items.append((section, [link]))
                        h2_sections[heading_text] = {
                            'section': section,
                            'link': link,
                            'items': []
                        }
                        current_h2 = heading_text
                        current_h1 = None
                    else:
                        chapter_items.append(link)
                
                if chapter_items:
                    chapter_section = epub.Section(chapter_title)
                    toc.append((chapter_section, chapter_items))
                else:
                    toc.append(chapter_link)
            
            self.book.toc = toc
        
        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())
        
        style = 'body { font-family: Times, Times New Roman, serif; }'
        nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
        self.book.add_item(nav_css)
        
        self.book.spine = ['nav'] + chapters
        self.log("目录生成完成")
    
    def save_epub(self, output_path):
        """保存EPUB文件"""
        if not self.book:
            raise ValueError("请先创建书籍")
        
        self.log(f"保存EPUB文件到: {output_path}")
        
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        epub.write_epub(output_path, self.book, {})
        return output_path
    
    def convert_markdown_to_epub(self, input_path, output_path, title, author, cover_path=None, custom_toc=None, images_dir=None, toc_type="auto"):
        """将Markdown转换为EPUB的主函数"""
        self.log("开始转换...")
        
        self.create_book(title, author, cover_path)
        self.images_dir = images_dir
        
        if os.path.isfile(input_path) and input_path.endswith('.md'):
            chapters = [self.add_markdown_file(input_path)]
        elif os.path.isdir(input_path):
            chapters = self.add_markdown_directory(input_path)
        else:
            raise ValueError("输入路径必须是Markdown文件或包含Markdown文件的目录")
        
        self.generate_toc(chapters, custom_toc, toc_type)
        
        return self.save_epub(output_path)
