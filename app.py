import os
import json
import yaml
import markdown
import requests
import sys
from flask import Flask, render_template, jsonify, send_from_directory, abort
from datetime import datetime
import jinja2
import shutil
import time
from datetime import timedelta
import calendar

app = Flask(__name__)

# 全局配置变量
config = None

# 修复：Flask 2.0+ 已废弃 before_first_request，改用 before_request + 判空
@app.before_request
def load_config():
    global config
    if config is not None:
        return  # 已加载过配置，直接返回
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        # 如果config.json不存在，尝试从default文件夹复制
        default_config_path = os.path.join('default', 'default_config.json')
        if os.path.exists(default_config_path):
            print(f"config.json不存在，从{default_config_path}复制默认配置")
            shutil.copy2(default_config_path, 'config.json')
            # 读取复制过来的配置
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 同时检查background.jpg是否存在，如果不存在也从default文件夹复制
            if 'background' in config and 'image' in config['background']:
                background_image = config['background']['image']
                if not os.path.exists(background_image) and os.path.exists(os.path.join('default', background_image)):
                    print(f"{background_image}不存在，从default文件夹复制")
                    shutil.copy2(os.path.join('default', background_image), background_image)
        else:
            # 如果default_config.json也不存在，使用内置默认配置
            print("default/default_config.json不存在，使用内置默认配置")
            config = {
                "github_url": "https://github.com/cicadaas-design",  # 改为你的GitHub地址
                "dark_mode": "auto",
                "name": "cicadaas",
                "bio": "数学建模爱好者，Python编程爱好者，AI技术爱好者",
                "introduction_file": "Introduction.md",
                "github_token": "",  # 可选：填写你的GitHub令牌（ghp_xxx）
                "theme": {
                    "primary_color": "#333333",
                    "secondary_color": "#555555",
                    "dark_primary_color": "#222222",
                    "dark_secondary_color": "#444444"
                },
                "background": {
                    "image": "background.jpg",
                    "blur": 8,
                    "overlay_opacity": 0.9,
                    "overlay_color": "#ffffff"
                }
            }
            # 保存默认配置
            with open('config.json', 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

# 创建通用的GitHub API请求函数
def make_github_request(url, timeout=5):
    try:
        # 配置requests不验证SSL证书（解决本地环境中的证书验证问题）
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        
        # 准备请求头
        headers = {'Accept': 'application/vnd.github.v3+json'}
        github_token = ''
        
        # 首先尝试从github_token.txt文件中读取令牌
        token_file = os.path.join(app.root_path, 'github_token.txt')
        try:
            if os.path.exists(token_file):
                with open(token_file, 'r', encoding='utf-8') as f:
                    github_token = f.read().strip()
                # 移除可能的空白字符和引号
                github_token = github_token.replace('"', '').replace("'", '')
                print(f"从github_token.txt文件中读取令牌成功")
            else:
                # 如果文件不存在，尝试从配置中获取
                github_token = config.get('github_token', '')
                print("github_token.txt文件不存在，尝试从配置中获取令牌")
        except Exception as e:
            print(f"读取GitHub令牌时出错: {e}")
            # 出错时，尝试从配置中获取
            github_token = config.get('github_token', '')
        
        # 如果配置了GitHub令牌，添加到请求头
        if github_token:
            headers['Authorization'] = f'token {github_token}'
            print(f"使用GitHub令牌进行认证")
        else:
            print("未使用GitHub令牌，使用匿名访问")
        
        # 发送请求
        response = requests.get(url, headers=headers, timeout=timeout, verify=False)
        print(f"GitHub API请求: {url}, 状态码: {response.status_code}")
        
        # 检查是否达到速率限制
        if response.status_code == 403 and 'rate limit' in response.text.lower():
            print("GitHub API速率限制已达，建议配置GitHub令牌")
        
        return response
    except Exception as e:
        print(f"GitHub API请求异常: {e}")
        # 创建一个模拟的响应对象
        class MockResponse:
            def __init__(self):
                self.status_code = 500
                self.text = "模拟错误响应"
        return MockResponse()

# 从 GitHub API 获取用户信息
def get_github_user_info():
    print("开始获取GitHub用户信息")
    github_url = config.get('github_url', 'https://github.com/example')
    username = github_url.rstrip('/').split('/')[-1]
    print(f"配置的GitHub URL: {github_url}")
    print(f"提取的用户名: {username}")

    try:
        print(f"准备请求GitHub API: https://api.github.com/users/{username}")
        
        # 获取用户信息
        user_response = make_github_request(f'https://api.github.com/users/{username}')
        print(f"GitHub API响应状态码: {user_response.status_code}")

        if user_response.status_code == 200:
            user_data = user_response.json()
            print(f"成功获取用户数据: {user_data.get('name')}, {user_data.get('login')}")

            # 获取用户的仓库信息
            repos_response = make_github_request(f'https://api.github.com/users/{username}/repos?sort=pushed&per_page=100')
            if repos_response.status_code == 200:
                repos = repos_response.json()

                # 获取总仓库数和总 stars 数
                total_repos = len(repos)
                total_stars = sum(repo.get('stargazers_count', 0) for repo in repos)

                # 获取同名仓库的 README
                readme_content = get_readme_content(username)

                # 获取最近有推送的 5 个仓库
                recent_repos = sorted(repos, key=lambda x: x.get('pushed_at', ''), reverse=True)[:5]

                # 获取用户的活动数据（过去12个月的提交统计）
                activity_data = get_github_activity_data(username, repos)

                # 分析用户的技术栈
                tech_stack = analyze_tech_stack(repos)

                return {
                    "avatar_url": user_data.get('avatar_url'),
                    "name": user_data.get('name') or username,
                    "bio": config.get('bio', 'Python Developer'),  # 使用配置文件中的bio
                    "total_repos": total_repos,
                    "total_stars": total_stars,
                    "readme_content": readme_content,
                    "recent_repos": recent_repos,
                    "activity_data": activity_data,
                    "tech_stack": tech_stack
                }
    except Exception as e:
        print(f"GitHub API调用异常: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # 如果获取失败，返回默认值
    return {
        "avatar_url": "https://avatars.githubusercontent.com/u/142971357?v=4",
        "name": config.get('name', 'cicadaas'),
        "bio": config.get('bio', '数学建模爱好者，Python编程爱好者，AI技术爱好者'),
        "total_repos": 0,
        "total_stars": 0,
        "readme_content": get_local_readme(),
        "recent_repos": [],
        "activity_data": [65, 59, 80, 81, 56, 55, 70, 65, 85, 75, 60, 75],  # 默认数据
        "tech_stack": [
            {"name": "Python", "color": "#333333"},
            {"name": "数学建模", "color": "#555555"},
            {"name": "HTML/CSS", "color": "#222222"},
            {"name": "Flask", "color": "#444444"}
        ]
    }

# 获取用户的GitHub活动数据（过去12个月的推送统计）
def get_github_activity_data(username, repos=None):
    try:
        print(f"开始获取GitHub活动数据: {username}")
        
        # 创建一个过去12个月的计数器
        now = datetime.now()
        activity_counts = [0] * 12  # 初始化过去12个月的计数
        earliest_date = now - timedelta(days=365)  # 过去一年的日期
        
        # 1. 尝试通过用户Events API获取PushEvent数据
        page = 1
        max_pages = 5
        event_found = False
        
        while page <= max_pages:
            events_url = f"https://api.github.com/users/{username}/events?page={page}&per_page=100"
            events_response = make_github_request(events_url)
            
            if events_response.status_code != 200:
                print(f"无法获取事件数据，状态码: {events_response.status_code}")
                break
            
            events = events_response.json()
            if not events:
                break
            
            # 处理每个事件
            page_has_recent_events = False
            for event in events:
                if event['type'] == 'PushEvent':
                    event_found = True
                    event_date_str = event['created_at']
                    event_date = datetime.strptime(event_date_str, '%Y-%m-%dT%H:%M:%SZ')
                    
                    if event_date >= earliest_date:
                        page_has_recent_events = True
                        years_diff = now.year - event_date.year
                        months_diff = now.month - event_date.month
                        
                        if now.day < event_date.day:
                            months_diff -= 1
                            if months_diff < 0:
                                years_diff -= 1
                                months_diff = 11
                        
                        total_months_diff = years_diff * 12 + months_diff
                        if 0 <= total_months_diff < 12:
                            activity_counts[total_months_diff] += 1
            
            page += 1
        
        # 2. 使用仓库提交历史作为补充
        if repos and len(repos) > 0:
            print("使用仓库提交历史作为补充数据")
            if len(repos) > 5:
                repos = repos[:5]
            
            for repo in repos:
                try:
                    commits_url = f"https://api.github.com/repos/{username}/{repo['name']}/commits?author={username}&per_page=100"
                    commits_response = make_github_request(commits_url)
                    
                    if commits_response.status_code == 200:
                        commits = commits_response.json()
                        for commit in commits:
                            commit_date_str = commit['commit']['author']['date']
                            commit_date = datetime.strptime(commit_date_str, '%Y-%m-%dT%H:%M:%SZ')
                            
                            if commit_date >= earliest_date:
                                years_diff = now.year - commit_date.year
                                months_diff = now.month - commit_date.month
                                
                                if now.day < commit_date.day:
                                    months_diff -= 1
                                    if months_diff < 0:
                                        years_diff -= 1
                                        months_diff = 11
                                
                                total_months_diff = years_diff * 12 + months_diff
                                if 0 <= total_months_diff < 12:
                                    activity_counts[total_months_diff] += 1
                except Exception as e:
                    print(f"获取仓库 {repo['name']} 的提交历史时出错: {e}")
                    continue
        
        # 3. 调整数据顺序（从最旧到最新）
        ordered_activity = []
        current_month = now.month
        for i in range(12):
            month_index = (now.month - 1 - i) % 12
            ordered_activity.append(activity_counts[month_index])
        ordered_activity = ordered_activity[::-1]
        
        # 4. 数据兜底
        if sum(ordered_activity) == 0:
            print("没有获取到活动数据，返回默认数据")
            return [65, 59, 80, 81, 56, 55, 70, 65, 85, 75, 60, 75]
        
        # 5. 平滑处理
        smoothed_data = []
        for i in range(12):
            values = [ordered_activity[i]]
            if i > 0:
                values.append(ordered_activity[i-1])
            if i < 11:
                values.append(ordered_activity[i+1])
            
            avg_value = int(sum(values) / len(values))
            min_value = min(values)
            smoothed_data.append(max(avg_value, int(min_value * 0.8)))
        
        # 6. 限制最大值
        max_value = max(smoothed_data)
        if max_value > 200:
            scaled_data = []
            for v in smoothed_data:
                if v > 200:
                    scaled_data.append(int(v * 200 / max_value))
                else:
                    scaled_data.append(v)
            return scaled_data
        
        return smoothed_data
    except Exception as e:
        print(f"获取GitHub活动数据异常: {e}")
    return [65, 59, 80, 81, 56, 55, 70, 65, 85, 75, 60, 75]

# 分析用户的技术栈（带缓存）
cached_tech_stack = None
cached_timestamp = 0
CACHE_DURATION = 3600  # 缓存1小时
def analyze_tech_stack(repos):
    global cached_tech_stack, cached_timestamp
    current_time = time.time()
    if cached_tech_stack and (current_time - cached_timestamp < CACHE_DURATION):
        print("使用缓存的技术栈数据")
        return cached_tech_stack
    
    try:
        print("开始分析用户的技术栈")
        language_stats = {}
        total_bytes = 0
        
        # 限制处理前10个仓库
        if len(repos) > 10:
            repos = repos[:10]
        
        # 遍历仓库统计语言
        for repo in repos:
            if 'language' in repo and repo['language']:
                lang = repo['language']
                if lang not in language_stats:
                    language_stats[lang] = 1
                else:
                    language_stats[lang] += 1
            
            if len(language_stats) < 5 and 'languages_url' in repo:
                try:
                    languages_response = make_github_request(repo['languages_url'])
                    if languages_response.status_code == 200:
                        languages_data = languages_response.json()
                        for lang, bytes_count in languages_data.items():
                            if lang not in language_stats:
                                language_stats[lang] = 0
                            language_stats[lang] += bytes_count
                            total_bytes += bytes_count
                except Exception as e:
                    print(f"获取仓库 {repo['name']} 的语言信息时出错: {e}")
                    continue
        
        # 兜底默认技术栈
        if not language_stats:
            print("没有获取到语言数据，返回默认技术栈")
            cached_tech_stack = [
                {"name": "Python", "color": "#333333"},
                {"name": "数学建模", "color": "#555555"},
                {"name": "HTML/CSS", "color": "#222222"},
                {"name": "Flask", "color": "#444444"}
            ]
            cached_timestamp = time.time()
            return cached_tech_stack
        
        # 排序取前10
        language_ratios = {lang: bytes_count for lang, bytes_count in language_stats.items()}
        sorted_languages = sorted(language_ratios.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # 生成颜色
        theme = config.get('theme', {
            'primary_color': '#333333',
            'secondary_color': '#555555',
            'dark_primary_color': '#222222',
            'dark_secondary_color': '#444444'
        })
        
        def generate_harmonious_color(base_color, index, is_dark=False):
            hex_color = base_color.lstrip('#')
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            
            factor = 1.0 - (index * 0.15)
            if factor < 0.4:
                factor = 0.4
            
            if is_dark:
                factor = 0.6 + (index * 0.1)
                if factor > 0.9:
                    factor = 0.9
            
            r = int(r * factor)
            g = int(g * factor)
            b = int(b * factor)
            return f'#{r:02x}{g:02x}{b:02x}'
        
        is_dark = config.get('dark_mode', 'auto') == 'dark'
        if is_dark:
            base_colors = [theme['dark_primary_color'], theme['dark_secondary_color']]
        else:
            base_colors = [theme['primary_color'], theme['secondary_color']]
        
        color_map = {
            'Python': generate_harmonious_color(base_colors[0], 0, is_dark),
            'JavaScript': generate_harmonious_color(base_colors[1], 0, is_dark),
            'Java': generate_harmonious_color(base_colors[0], 1, is_dark),
            'TypeScript': generate_harmonious_color(base_colors[1], 1, is_dark),
            'HTML': generate_harmonious_color(base_colors[0], 2, is_dark),
            'CSS': generate_harmonious_color(base_colors[1], 2, is_dark),
            'Flask': generate_harmonious_color(base_colors[0], 3, is_dark),
            'Django': generate_harmonious_color(base_colors[1], 3, is_dark)
        }
        
        # 构建技术栈列表（合并HTML/CSS）
        tech_stack = []
        html_css_exists = False
        for lang, _ in sorted_languages:
            if lang == 'HTML' or lang == 'CSS':
                if not html_css_exists:
                    tech_stack.append({"name": "HTML/CSS", "color": color_map.get('HTML', '#222222')})
                    html_css_exists = True
            else:
                tech_stack.append({"name": lang, "color": color_map.get(lang, '#444444')})
        
        # 确保不超过10个
        tech_stack = tech_stack[:10]
        cached_tech_stack = tech_stack
        cached_timestamp = time.time()
        print(f"分析完成的技术栈: {[tech['name'] for tech in tech_stack]}")
        return tech_stack
    except Exception as e:
        print(f"分析技术栈时发生异常: {e}")
        return [
            {"name": "Python", "color": "#333333"},
            {"name": "数学建模", "color": "#555555"},
            {"name": "HTML/CSS", "color": "#222222"},
            {"name": "Flask", "color": "#444444"}
        ]

# 获取GitHub仓库README
def get_readme_content(username):
    try:
        print(f"尝试获取GitHub同名仓库README: {username}/{username}")
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        
        # 尝试main分支
        readme_url_main = f'https://raw.githubusercontent.com/{username}/{username}/main/README.md'
        readme_response = requests.get(readme_url_main, timeout=5, verify=False)
        if readme_response.status_code == 200:
            print("成功获取main分支的README")
            return markdown.markdown(readme_response.text)
        
        # 尝试master分支
        readme_url_master = f'https://raw.githubusercontent.com/{username}/{username}/master/README.md'
        readme_response = requests.get(readme_url_master, timeout=5, verify=False)
        if readme_response.status_code == 200:
            print("成功获取master分支的README")
            return markdown.markdown(readme_response.text)
        
        print(f"GitHub README获取失败，状态码: {readme_response.status_code}")
    except Exception as e:
        print(f"GitHub README获取异常: {type(e).__name__}: {str(e)}")
    
    # 读取本地README
    print("使用本地README文件")
    return get_local_readme()

# 读取本地README
def get_local_readme():
    try:
        introduction_file = config.get('introduction_file', 'Introduction.md')
        if os.path.exists(introduction_file):
            with open(introduction_file, 'r', encoding='utf-8') as f:
                return markdown.markdown(f.read())
    except Exception:
        pass
    return "<p>欢迎访问我的个人主页！我是一名数学建模爱好者、Python编程爱好者和AI技术爱好者～</p>"

# 主页路由
@app.route('/')
def index():
    github_info = get_github_user_info()
    
    # 检查背景图片
    background_image = config.get('background', {}).get('image', 'background.jpg')
    possible_paths = [
        os.path.join(os.getcwd(), background_image),
        os.path.join(os.getcwd(), 'static', background_image)
    ]
    
    background_exists = False
    background_path = background_image
    for path in possible_paths:
        if os.path.exists(path):
            background_exists = True
            if 'static' in path:
                background_path = f'/static/{background_image}'
            break
    
    print(f"背景图片配置: {background_image}, 存在: {background_exists}")
    return render_template('index.html', 
                          github_info=github_info, 
                          config=config,
                          now=datetime.now(),
                          background_exists=background_exists,
                          background_path=background_path)

# 配置API
@app.route('/api/config')
def get_config():
    return jsonify(config)

# 静态文件访问
@app.route('/<path:filename>')
def serve_root_file(filename):
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.css', '.js'}
    file_ext = os.path.splitext(filename)[1].lower()
    
    if file_ext in allowed_extensions:
        try:
            return send_from_directory(os.getcwd(), filename)
        except FileNotFoundError:
            abort(404)
    abort(404)

# 生成静态HTML（用于GitHub Pages部署）
def generate_static_html():
    print("开始生成静态HTML文件...")
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static_build')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)
    else:
        for file in os.listdir(static_dir):
            file_path = os.path.join(static_dir, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
    
    try:
        # 加载配置
        global config
        if config is None:
            try:
                with open('config.json', 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except FileNotFoundError:
                config = {
                    "github_url": "https://github.com/cicadaas-design",
                    "dark_mode": "auto",
                    "name": "cicadaas",
                    "bio": "数学建模爱好者，Python编程爱好者，AI技术爱好者",
                    "introduction_file": "Introduction.md",
                    "github_token": "",
                    "theme": {
                        "primary_color": "#333333",
                        "secondary_color": "#555555",
                        "dark_primary_color": "#222222",
                        "dark_secondary_color": "#444444"
                    },
                    "background": {
                        "image": "background.jpg",
                        "blur": 8,
                        "overlay_opacity": 0.9,
                        "overlay_color": "#ffffff"
                    }
                }
        
        # 读取介绍内容
        introduction_content = ""
        if 'introduction_file' in config and os.path.exists(config['introduction_file']):
            try:
                with open(config['introduction_file'], 'r', encoding='utf-8') as f:
                    introduction_content = f.read()
                introduction_content = markdown.markdown(introduction_content)
            except Exception as e:
                print(f"警告：无法读取或解析介绍文件: {e}")
        
        # 渲染模板
        template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=jinja2.select_autoescape(['html', 'xml'])
        )
        template = env.get_template('index.html')
        
        # 获取GitHub信息
        github_info = get_github_user_info()
        
        render_args = {
            'config': config,
            'github_info': github_info,
            'now': datetime.now(),
            'background_exists': os.path.exists(config.get('background', {}).get('image', 'background.jpg')),
            'background_path': config.get('background', {}).get('image', 'background.jpg')
        }
        
        html_content = template.render(**render_args)
        html_path = os.path.join(static_dir, 'index.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"静态HTML文件已保存到: {html_path}")
        
        # 复制静态资源
        resources_to_copy = []
        if 'background' in config and 'image' in config['background']:
            background_image = config['background']['image']
            if os.path.exists(background_image):
                resources_to_copy.append(background_image)
        
        for file in ['background.jpg', 'favicon.ico']:
            if os.path.exists(file):
                resources_to_copy.append(file)
        
        for resource in resources_to_copy:
            try:
                dst = os.path.join(static_dir, os.path.basename(resource))
                shutil.copy(resource, dst)
                print(f"已复制资源文件: {resource}")
            except Exception as e:
                print(f"警告：无法复制资源文件 {resource}: {e}")
        
        print("\n静态文件生成成功！部署命令参考：")
        print("cd static_build")
        print("git init && git add . && git commit -m 'Deploy'")
        print("git remote add origin https://github.com/cicadaas-design/cicadaas-design.github.io.git")
        print("git push -f origin master:gh-pages")
        
    except Exception as e:
        print(f"错误：生成静态文件失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    return True

# 启动入口
if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'generate_static':
        generate_static_html()
    else:
        os.environ['FLASK_APP'] = 'app.py'
        app.run(debug=True, host='0.0.0.0', port=5000)
