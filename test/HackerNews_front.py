import requests
from bs4 import BeautifulSoup
import time
import json
import random
import re

def fetch_article_content(url, headers):
    """
    智能抓取链接内容：
    - 如果是 GitHub 仓库，抓取 README.md
    - 否则，抓取整个页面的可见文本
    """
    if not url:
        return ""
    
    # 判断是否为 GitHub 仓库链接
    github_repo_pattern = r'https?://github\.com/([^/]+)/([^/]+)'
    match = re.match(github_repo_pattern, url)
    
    if match:
        # 是 GitHub 仓库，构建 README.md 的原始内容 URL
        owner, repo = match.groups()
        # 去除可能存在的末尾斜杠或多余路径
        repo = repo.split('/')[0]
        return fetch_github_readme(owner, repo, headers)
    else:
        # 普通网页，抓取全部可见文本
        return fetch_page_text(url, headers)

def fetch_github_readme(owner, repo, headers):
    """获取 GitHub 仓库的 README.md 原始内容，尝试 main/master 分支"""
    base_raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}"
    
    for branch in ['main', 'master']:
        readme_url = f"{base_raw_url}/{branch}/README.md"
        try:
            response = requests.get(readme_url, headers=headers, timeout=10)
            if response.status_code == 200:
                print(f"      成功获取 README: {readme_url}")
                return response.text[:5000]  # 限制最大5000字符，避免输出过长
            # 遇到 429 则重试
            elif response.status_code == 429:
                print(f"      遇到 429，等待 30 秒后重试...")
                time.sleep(30)
                continue
        except Exception as e:
            print(f"      获取 README 失败 ({readme_url}): {e}")
            time.sleep(2)
    
    print(f"      警告: 无法获取 {owner}/{repo} 的 README.md")
    return ""

def fetch_page_text(url, headers, max_retries=2):
    """抓取普通网页的文本内容（提取 <body> 中的所有可见文本）"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            
            if response.status_code == 429:
                wait = 30 + attempt * 15
                print(f"      遇到 429，等待 {wait} 秒...")
                time.sleep(wait)
                continue
                
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除脚本、样式等无关标签
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                tag.decompose()
            
            # 获取 <body> 或整个文档的文本
            body = soup.find('body')
            text = body.get_text(separator='\n', strip=True) if body else soup.get_text(separator='\n', strip=True)
            
            # 简单清理：合并多余空行，限制长度
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            cleaned_text = '\n'.join(lines)
            print(f"      成功获取页面内容，长度: {len(cleaned_text)} 字符")
            return cleaned_text[:8000]  # 限制最大8000字符
            
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"      抓取页面最终失败: {url} - {e}")
                return ""
            time.sleep(5)
    
    return ""

def fetch_comments(comment_url, headers, max_comments=20, retries=3):
    """请求评论页面，解析并返回前N条评论，遇到429错误时自动重试"""
    for attempt in range(retries):
        try:
            response = requests.get(comment_url, headers=headers, timeout=15)
            
            if response.status_code == 429:
                wait_time = 30 + (attempt * 15)
                print(f"    收到 429 错误，将在 {wait_time} 秒后重试 (尝试 {attempt+1}/{retries})...")
                time.sleep(wait_time)
                continue
                
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            comment_divs = soup.find_all('div', class_='commtext')
            
            comments = []
            for div in comment_divs[:max_comments]:
                comment_text = div.get_text(strip=True)
                if comment_text:
                    comments.append({"content": comment_text})
            
            return comments
            
        except requests.exceptions.RequestException as e:
            if attempt == retries - 1:
                print(f"    抓取评论最终失败: {comment_url} - {e}")
                return []
            else:
                wait_time = 10 + (attempt * 5)
                print(f"    请求异常，{wait_time}秒后重试: {e}")
                time.sleep(wait_time)
    
    return []

def fetch_hackernews_front_with_comments(max_items=30, max_comments=20):
    """主函数：抓取HN头条，包括评论和文章内容"""
    base_url = "https://news.ycombinator.com"
    front_url = f"{base_url}/front"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    results = []

    try:
        print(f"正在请求列表页: {front_url}")
        response = requests.get(front_url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        items = soup.find_all('tr', class_='athing')
        print(f"找到 {len(items)} 条新闻，将处理前 {max_items} 条。")

        for i, item in enumerate(items):
            if i >= max_items:
                break
            
            # --- 解析列表页信息（同之前）---
            item_id = item.get('id')
            title_element = item.find('span', class_='titleline')
            if not title_element:
                continue
                
            link_tag = title_element.find('a')
            title = link_tag.get_text(strip=True) if link_tag else '无标题'
            news_url = link_tag.get('href') if link_tag else ''
            if news_url.startswith('item?'):
                news_url = f"{base_url}/{news_url}"
            
            subtext_row = item.find_next_sibling('tr')
            score = author = comment_count = "未知"
            comment_url = ""
            
            if subtext_row:
                subtext = subtext_row.find('td', class_='subtext')
                if subtext:
                    score_tag = subtext.find('span', class_='score')
                    if score_tag:
                        score = score_tag.get_text(strip=True)
                    
                    author_tag = subtext.find('a', class_='hnuser')
                    if author_tag:
                        author = author_tag.get_text(strip=True)
                    
                    comment_links = subtext.find_all('a')
                    for link in comment_links:
                        if 'comment' in link.get_text(strip=True):
                            comment_text = link.get_text(strip=True)
                            comment_count = comment_text.split('\u00a0')[0] if '\u00a0' in comment_text else comment_text
                            comment_url = f"{base_url}/{link.get('href')}"
                            break
            
            print(f"  [{i+1}/{max_items}] {title}")

            # --- 新增：抓取文章内容 ---
            article_content = ""
            if news_url and not news_url.startswith(base_url):  # 避免抓取HN自身链接
                print(f"    正在抓取文章内容: {news_url}")
                article_content = fetch_article_content(news_url, headers)
                # 抓完文章后等待一段时间
                time.sleep(random.uniform(2, 5))
            
            # --- 抓取评论 ---
            comments = []
            if comment_url:
                comments = fetch_comments(comment_url, headers, max_comments)
                # 抓完评论后等待
                delay = random.uniform(3, 8)
                print(f"    等待 {delay:.1f} 秒...")
                time.sleep(delay)
            else:
                time.sleep(random.uniform(1, 3))
            
            # --- 整合数据 ---
            results.append({
                "id": item_id,
                "title": title,
                "url": news_url,
                "score": score,
                "author": author,
                "comment_count": comment_count,
                "comment_url": comment_url,
                "comments": comments,
                "article_content": article_content  # 新字段：文章内容
            })
        
        return {
            "status": "success",
            "source": front_url,
            "items_count": len(results),
            "items": results
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    # 抓取全部30条新闻，每条最多获取20条评论，并抓取文章内容
    data = fetch_hackernews_front_with_comments(max_items=30, max_comments=20)
    
    # 保存为 JSON 文件
    with open('hackernews_full_with_content.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n完成！数据已保存到 hackernews_full_with_content.json")
    print(f"共处理 {data.get('items_count', 0)} 条新闻。")
    
    # 简要统计文章内容获取情况
    if data['status'] == 'success':
        for item in data['items']:
            content_len = len(item.get('article_content', ''))
            print(f"- {item['title'][:60]}... | 文章长度: {content_len} 字符 | 评论: {len(item['comments'])} 条")