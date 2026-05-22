import requests
import json
import re
from datetime import datetime, timezone

def get_repo_description(repo_id, repo_type="model"):
    """
    侦察兵函数：去原始 README.md 中提取第一段有效文本作为项目简介
    """
    # 构造 raw 内容的下载链接
    if repo_type == "space":
        url = f"https://huggingface.co/spaces/{repo_id}/raw/main/README.md"
    else:
        url = f"https://huggingface.co/{repo_id}/raw/main/README.md"
    
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            content = res.text
            # 按行拆分
            lines = content.split('\n')
            
            for line in lines:
                line = line.strip()
                # 过滤掉 Markdown 标题 (#)、图片 (![)、YAML 元数据 (---)、HTML 标签 (<)
                if line and not line.startswith(('#', '![', '---', '<')):
                    # 找到第一段长度大于 40 个字符的文本（避免抓到短语或作者名字）
                    if len(line) > 40:
                        # 简单清洗：去掉 markdown 的超链接格式 [text](url) 保留 text
                        clean_line = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line)
                        # 清洗粗体、斜体和代码块标记
                        clean_line = clean_line.replace('**', '').replace('*', '').replace('`', '')
                        
                        # 截断过长文本，保持日报整洁
                        return clean_line[:250] + "..." if len(clean_line) > 250 else clean_line
    except Exception:
        pass
    
    return "（该项目暂无详细文字简介或 README 解析失败）"

def generate_hf_daily_report(date_str=None, top_n=5):
    """
    获取 Hugging Face 每日综合报告
    """
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    print(f"🚀 开始生成 Hugging Face 深度日报数据 ({date_str})...\n")
    
    headers = {
        'User-Agent': 'HF-Daily-Report-Bot/2.0',
        'Accept': 'application/json'
    }
    
    report_data = {
        "report_date": date_str,
        "trending_papers": [],
        "trending_models": [],
        "trending_spaces": []
    }

    # ==========================================
    # 1. 获取每日论文 (不变)
    # ==========================================
    print("📚 正在获取每日最热论文...")
    try:
        papers_url = "https://huggingface.co/api/daily_papers"
        res_papers = requests.get(papers_url, params={"date": date_str}, headers=headers, timeout=10)
        res_papers.raise_for_status()
        papers = res_papers.json()
        
        for p in papers[:top_n]:
            paper_info = p.get('paper', {})
            report_data["trending_papers"].append({
                "title": paper_info.get('title', '无标题'),
                "arxiv_id": paper_info.get('id', ''),
                "url": f"https://huggingface.co/papers/{paper_info.get('id', '')}",
                "upvotes": p.get('upvotes', 0),
                "abstract": paper_info.get('summary', '').replace('\n', ' ').strip()[:300] + "..."
            })
    except Exception as e:
        print(f"❌ 获取论文失败: {e}")

    # ==========================================
    # 2. 获取热门模型 (升级：加入描述提取)
    # ==========================================
    print("🤖 正在获取 Trending 热门模型（并提取介绍）...")
    try:
        models_url = "https://huggingface.co/api/models"
        res_models = requests.get(models_url, params={"sort": "trendingScore", "limit": top_n}, headers=headers, timeout=10)
        res_models.raise_for_status()
        models = res_models.json()
        
        for m in models:
            model_id = m.get('id')
            print(f"  -> 解析模型: {model_id}")
            description = get_repo_description(model_id, repo_type="model")
            
            report_data["trending_models"].append({
                "model_id": model_id,
                "url": f"https://huggingface.co/{model_id}",
                "task_type": m.get('pipeline_tag', '未知类型'), 
                "downloads": m.get('downloads', 0),
                "likes": m.get('likes', 0),
                "description": description # 🔥 新增简介字段
            })
    except Exception as e:
        print(f"❌ 获取模型失败: {e}")

    # ==========================================
    # 3. 获取热门 Spaces (升级：加入描述提取)
    # ==========================================
    print("🎮 正在获取 Trending 热门应用 Spaces（并提取介绍）...")
    try:
        spaces_url = "https://huggingface.co/api/spaces"
        res_spaces = requests.get(spaces_url, params={"sort": "trendingScore", "limit": top_n}, headers=headers, timeout=10)
        res_spaces.raise_for_status()
        spaces = res_spaces.json()
        
        for s in spaces:
            space_id = s.get('id')
            print(f"  -> 解析 Space: {space_id}")
            description = get_repo_description(space_id, repo_type="space")
            
            report_data["trending_spaces"].append({
                "space_id": space_id,
                "url": f"https://huggingface.co/spaces/{space_id}",
                "framework": s.get('sdk', '未知框架'), 
                "likes": s.get('likes', 0),
                "description": description # 🔥 新增简介字段
            })
    except Exception as e:
        print(f"❌ 获取 Spaces 失败: {e}")

    print("\n✅ 数据抓取完成！")
    return report_data

if __name__ == "__main__":
    daily_report = generate_hf_daily_report(top_n=5)
    
    output_filename = f"hf_report_rich_{daily_report['report_date']}.json"
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(daily_report, f, indent=4, ensure_ascii=False)
        
    print(f"📄 深度报告已保存至 {output_filename}")