"""
cron "0 8 * * *" script-path=nodeseek_checkin.py,tag=匹配cron用
new Env('NodeSeek论坛签到')
"""

import os
import re
import requests
import random
import time
from datetime import datetime, timedelta  # ✅ 修复：补齐 timedelta 导入

# ---------------- 统一通知模块加载 ----------------
hadsend = False
send = None
try:
    from notify import send
    hadsend = True
    print("✅ 已加载notify.py通知模块")
except ImportError:
    print("⚠️ 未加载通知模块，跳过通知功能")

# 配置项
NODESEEK_COOKIE = os.environ.get('NODESEEK_COOKIE', '')
max_random_delay = int(os.getenv("MAX_RANDOM_DELAY", "3600"))
random_signin = os.getenv("RANDOM_SIGNIN", "true").lower() == "true"
privacy_mode = os.getenv("PRIVACY_MODE", "true").lower() == "true"

# NodeSeek 配置
BASE_URL = 'https://www.nodeseek.com'
USER_INFO_URL = f'{BASE_URL}/api/user/info'
CHECKIN_URL = f'{BASE_URL}/api/user/checkin'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'Referer': 'https://www.nodeseek.com/board',
    'Connection': 'keep-alive'
}

def mask_username(username):
    """用户名脱敏处理"""
    if not username:
        return username

    if privacy_mode:
        if len(username) <= 2:
            return '*' * len(username)
        elif len(username) <= 4:
            return username[0] + '*' * (len(username) - 2) + username[-1]
        else:
            return username[0] + '*' * 3 + username[-1]
    return username

def format_time_remaining(seconds):
    """格式化时间显示"""
    if seconds <= 0:
        return "立即执行"
    hours, minutes = divmod(seconds, 3600)
    minutes, secs = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}小时{minutes}分{secs}秒"
    elif minutes > 0:
        return f"{minutes}分{secs}秒"
    else:
        return f"{secs}秒"

def wait_with_countdown(delay_seconds, task_name):
    """带倒计时的随机延迟等待，并显示预计签到时间点"""
    if delay_seconds <= 0:
        return
    
    # 计算预计签到具体时间点
    eta_time = datetime.now() + timedelta(seconds=delay_seconds)
    eta_str = eta_time.strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"⏰ {task_name} 预计签到时间点: {eta_str}")
    print(f"{task_name} 需要等待 {format_time_remaining(delay_seconds)}")
    
    remaining = delay_seconds
    while remaining > 0:
        if remaining <= 10 or remaining % 10 == 0:
            print(f"{task_name} 倒计时: {format_time_remaining(remaining)} (预计时间: {eta_str})")
        sleep_time = 1 if remaining <= 10 else min(10, remaining)
        time.sleep(sleep_time)
        remaining -= sleep_time

def notify_user(title, content):
    """统一通知函数"""
    if hadsend:
        try:
            send(title, content)
            print(f"✅ 通知发送完成: {title}")
        except Exception as e:
            print(f"❌ 通知发送失败: {e}")
    else:
        print(f"📢 {title}\n📄 {content}")

def parse_cookies(cookie_str):
    """解析Cookie字符串，支持多账号"""
    if not cookie_str:
        return []

    lines = cookie_str.strip().split('\n')
    cookies = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        parts = line.split('&&')
        for part in parts:
            part = part.strip()
            if part:
                cookies.append(part)

    unique_cookies = []
    for cookie in cookies:
        if cookie and cookie not in unique_cookies:
            unique_cookies.append(cookie)

    return unique_cookies

class NodeSeekSigner:
    name = "NodeSeek论坛"

    def __init__(self, cookie: str, index: int = 1):
        self.cookie = cookie
        self.index = index
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.headers['Cookie'] = cookie

        # 用户信息字段
        self.user_name = None
        self.user_gain_before = None  # 签到前鸡腿数
        self.user_gain_after = None   # 签到后鸡腿数

    def get_user_info(self, is_after=False):
        """获取用户信息和鸡腿资产"""
        try:
            print(f"👤 正在获取{'签到后' if is_after else '签到前'}用户信息...")
            time.sleep(random.uniform(1.5, 3))

            response = self.session.get(USER_INFO_URL, timeout=20)
            
            if response.status_code != 200:
                print(f"🔍 响应状态码异常: {response.status_code}")
                return False, f"HTTP 状态码错误: {response.status_code}"

            res_json = response.json()
            if res_json.get('success') or 'username' in res_json:
                data = res_json.get('data', res_json) if isinstance(res_json.get('data'), dict) else res_json
                current_gain = data.get('gain', 0)

                if is_after:
                    self.user_gain_after = current_gain
                    print(f"🍗 签到后 - 鸡腿: {current_gain}")
                else:
                    self.user_gain_before = current_gain
                    self.user_name = data.get('username', '未知用户')
                    print(f"🍗 签到前 - 鸡腿: {current_gain}")
                    print(f"👤 用户: {mask_username(self.user_name)}")

                return True, "用户信息获取成功"
            else:
                return False, f"接口返回错误: {res_json.get('message', '未知错误')}"

        except Exception as e:
            error_msg = f"获取用户信息异常: {str(e)}"
            print(f"❌ {error_msg}")
            return False, error_msg

    def perform_checkin(self):
        """执行签到"""
        try:
            print("📝 正在执行签到...")
            payload = {"random": "false"} 
            
            response = self.session.post(CHECKIN_URL, json=payload, timeout=30)
            print(f"🔍 签到响应状态码: {response.status_code}")
            
            if response.status_code == 401:
                return False, "Cookie 已过期或失效"

            try:
                result = response.json()
            except ValueError:
                result = {"message": response.text}

            if isinstance(result, dict):
                success = result.get("success", False)
                message = str(result.get("message", "")).strip()

                if success is True:
                    return True, message or "签到成功"
                if "已签到" in message or "重复" in message or "连续签到" in message:
                    return True, message or "今日已签到"
                if message:
                    return False, f"签到失败: {message}"
            
            return False, "未知签到响应格式"

        except Exception as e:
            return False, f"签到异常: {str(e)}"

    def run(self):  # ✅ 修复：将 main 改名为 run，防止和全局 main 重名混淆
        """主执行函数"""
        print(f"\n==== NodeSeek 账号{self.index} 开始签到 ====")

        if not self.cookie.strip():
            error_msg = "账号配置错误: Cookie为空，请在青龙中配置 NODESEEK_COOKIE"
            print(f"❌ {error_msg}")
            return error_msg, False

        # 1. 获取签到前资产
        user_success, user_msg = self.get_user_info(is_after=False)
        if not user_success:
            print(f"⚠️ 获取签到前用户信息失败: {user_msg}")

        # 2. 随机等待
        time.sleep(random.uniform(2, 4))

        # 3. 执行签到
        signin_success, signin_msg = self.perform_checkin()

        # 4. 获取签到后资产
        time.sleep(random.uniform(2, 4))
        after_success, after_msg = self.get_user_info(is_after=True)

        # 5. 通过鸡腿变化判断
        gain_info = ""
        if user_success and after_success and self.user_gain_before is not None and self.user_gain_after is not None:
            try:
                gain_diff = int(self.user_gain_after) - int(self.user_gain_before)
                print(f"📊 鸡腿变化: {self.user_gain_before} → {self.user_gain_after} (+{gain_diff})")

                if gain_diff > 0:
                    signin_success = True
                    signin_msg = f"签到成功，获得 {gain_diff} 鸡腿"
                    gain_info = f"\n🎁 本次收益: +{gain_diff} 鸡腿"
                elif gain_diff == 0:
                    signin_success = True
                    if "失败" in signin_msg or not signin_success:
                        signin_msg = "今日已签到（鸡腿无变化）"
                    print("📅 鸡腿无变化，今日已签到")
            except Exception as e:
                print(f"⚠️ 资产变化计算异常: {e}")

        # 6. 组合结果消息
        final_msg = f"""🌟 NodeSeek 论坛签到结果

    👤 用户: {mask_username(self.user_name) or '未知用户'}
    🍗 鸡腿: {self.user_gain_before if self.user_gain_before is not None else '未知'} → {self.user_gain_after if self.user_gain_after is not None else (self.user_gain_before or '未知')}{gain_info}

    📝 签到: {signin_msg}
    ⏰ 时间: {datetime.now().strftime('%m-%d %H:%M')}"""

        print(f"{'✅ 任务完成' if signin_success else '❌ 任务失败'}")
        return final_msg, signin_success

def main():
    """主程序入口"""
    print(f"==== NodeSeek 签到开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")
    print(f"🔒 隐私保护模式: {'已启用' if privacy_mode else '已禁用'}")

    # 整体随机延迟
    if random_signin:
        delay_seconds = random.randint(0, max_random_delay)
        if delay_seconds > 0:
            print(f"🎲 随机延迟: {format_time_remaining(delay_seconds)}")
            wait_with_countdown(delay_seconds, "NodeSeek论坛签到")

    if not NODESEEK_COOKIE:
        error_msg = "❌ 未找到 NODESEEK_COOKIE 环境变量，请在面板中配置。"
        print(error_msg)
        notify_user("NodeSeek论坛签到失败", error_msg)
        return

    cookies = parse_cookies(NODESEEK_COOKIE)
    if not cookies:
        error_msg = "❌ Cookie解析失败，请检查格式。"
        print(error_msg)
        notify_user("NodeSeek论坛签到失败", error_msg)
        return

    print(f"📝 共发现 {len(cookies)} 个账号")

    success_count = 0
    total_count = len(cookies)
    results = []

    for index, cookie in enumerate(cookies):
        try:
            if index > 0:
                delay = random.uniform(10, 20)
                print(f"⏱️ 随机等待 {delay:.1f} 秒后处理下一个账号...")
                time.sleep(delay)

            signer = NodeSeekSigner(cookie, index + 1)
            result_msg, is_success = signer.run()  # ✅ 修复：配合上面改名为 run

            if is_success:
                success_count += 1

            results.append({
                'index': index + 1,
                'success': is_success,
                'message': result_msg,
                'username': mask_username(signer.user_name) if signer.user_name else f"账号{index + 1}"
            })

            status = "成功" if is_success else "失败"
            notify_user(f"NodeSeek 账号{index + 1}签到{status}", result_msg)

        except Exception as e:
            error_msg = f"账号{index + 1}: 执行异常 - {str(e)}"
            print(f"❌ {error_msg}")
            notify_user(f"NodeSeek 账号{index + 1}签到失败", error_msg)

    # 汇总通知
    if total_count > 1:
        summary_msg = f"""📊 NodeSeek 论坛签到汇总

📈 总计: {total_count}个账号
✅ 成功: {success_count}个
❌ 失败: {total_count - success_count}个
📊 成功率: {success_count/total_count*100:.1f}%
⏰ 完成时间: {datetime.now().strftime('%m-%d %H:%M')}"""

        if len(results) <= 5:
            summary_msg += "\n\n📋 详细结果:"
            for result in results:
                status_icon = "✅" if result['success'] else "❌"
                summary_msg += f"\n{status_icon} {result['username']}"

        notify_user("NodeSeek 论坛签到汇总", summary_msg)

    print(f"\n==== NodeSeek 签到完成 - 成功{success_count}/{total_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")

def handler(event, context):
    """云函数入口"""
    main()

if __name__ == "__main__":
    main()
