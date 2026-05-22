import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import time
import re

def fetch_readme_content(full_name):
    """
    根据仓库的 full_name (如 'tinyhumansai/openhuman') 获取 README.md 的原始文本内容。
    默认尝试 'main' 分支，失败则尝试 'master' 分支。
    """
    base_raw_url = f"https://raw.githubusercontent.com/{full_name}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }

    # 尝试两个常见的默认分支名
    for branch in ['main', 'master']:
        readme_url = f"{base_raw_url}/{branch}/README.md"
        try:
            response = requests.get(readme_url, headers=headers, timeout=10)
            if response.status_code == 200:
                print(f"成功获取 README: {readme_url}")
                return response.text
            # 如果不是404，可能是其他错误，但我们仍可尝试下一个分支
        except Exception as e:
            print(f"获取 {readme_url} 失败: {e}")
            continue
    
    print(f"警告: 无法获取 {full_name} 的 README.md (已尝试 main 和 master 分支)")
    return ""  # 或返回 None

def fetch_trending_direct():
    """
    直接解析 GitHub Trending 页面，并获取每个仓库的 README.md 内容。
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    url = 'https://github.com/trending'
    
    try:
        session = requests.Session()
        session.get('https://github.com', headers=headers, timeout=10)
        time.sleep(2)  # 礼貌性延迟
        
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        repo_list = []
        
        articles = soup.find_all('article', class_='Box-row')
        
        for article in articles:
            h2 = article.find('h2', class_='h3 lh-condensed')
            if not h2:
                continue
            
            # 提取完整的 "owner/repo" 名称
            a_tag = h2.find('a')
            if not a_tag:
                continue
            full_name = a_tag['href'].strip('/')  # 例如 '/tinyhumansai/openhuman' -> 'tinyhumansai/openhuman'
            
            # 提取纯仓库名（用于之前的显示，可选）
            repo_name_parts = full_name.split('/')
            simple_name = repo_name_parts[-1] if len(repo_name_parts) > 1 else full_name
            
            repo_url = 'https://github.com/' + full_name
            
            # 提取描述
            desc_p = article.find('p', class_='col-9 color-fg-muted my-1 pr-4')
            description = desc_p.get_text(strip=True) if desc_p else ''
            
            # 提取语言
            lang_span = article.find('span', itemprop='programmingLanguage')
            language = lang_span.get_text(strip=True) if lang_span else 'Unknown'
            
            # 提取今日星数
            stars_today = 0
            stars_span = article.find('span', class_='d-inline-block float-sm-right')
            if stars_span:
                stars_text = stars_span.get_text(strip=True).split()[0]
                try:
                    stars_today = int(stars_text.replace(',', ''))
                except ValueError:
                    pass
            
            # 核心新增：获取 README 内容
            print(f"正在处理: {full_name}...")
            readme_content = fetch_readme_content(full_name)
            time.sleep(1)  # 在请求之间添加延迟，避免触发速率限制
            
            repo_list.append({
                "name": full_name,  # 使用全名 'owner/repo' 更加明确
                "url": repo_url,
                "description": description,
                "language": language,
                "stars_today": stars_today,
                "readme": readme_content  # 新增字段
            })
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "count": len(repo_list),
            "repositories": repo_list
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    trending_data = fetch_trending_direct()
    
    # 由于 README 内容很长，为了便于在控制台查看，可以只打印结构或保存到文件
    # 保存到文件是更推荐的做法
    with open('github_trending_with_readme.json', 'w', encoding='utf-8') as f:
        json.dump(trending_data, f, indent=2, ensure_ascii=False)
    
    print(f"数据已保存至 github_trending_with_readme.json，共处理 {trending_data.get('count', 0)} 个仓库。")
    
    # 如果你想在控制台预览，可以只打印简要信息，跳过 readme 内容
    for repo in trending_data.get('repositories', []):
        print(f"- {repo['name']}: README 长度 {len(repo['readme'])} 字符")