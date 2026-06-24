# -*- coding: utf-8 -*-
"""
cron "0 8 * * *" script-path=checkIn_Quark.py,tag=匹配cron用
new Env('夸克自动签到')
"""

import os
import re
import sys
import requests
import random
import time
from datetime import datetime, timedelta

# ---------------- 统一通知模块加载 ----------------
hadsend = False
send = None
try:
    from notify import send
    hadsend = True
    print("✅ 已加载notify.py通知模块")
except ImportError:
    try:
        from utils.notify import send
        hadsend = True
        print("✅ 已加载utils.notify通知模块")
    except ImportError:
        print("⚠️  未加载通知模块，跳过通知功能")

# 配置项 - 同时兼容大写 QUARK_COOKIE 和小写 quark_cookie
quark_cookie = os.environ.get('QUARK_COOKIE') or os.environ.get('quark_cookie', '')
max_random_delay = int(os.getenv("MAX_RANDOM_DELAY", "3600"))
random_signin = os.getenv("RANDOM_SIGNIN", "true").lower() == "true"
privacy_mode = os.getenv("PRIVACY_MODE", "true").lower() == "true"

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
    """解析Cookie字符串，支持多账号 (以 && 或 换行 分隔)"""
    if not cookie_str:
        return []
    # 兼容换行和 && 分隔多账号
    lines = cookie_str.strip().replace('\n', '&&').split('&&')
    return [line.strip() for line in lines if line.strip()]

class QuarkSigner:
    name = "夸克网盘"

    def __init__(self, cookie_str: str, index: int = 1):
        self.index = index
        self.session = requests.Session()
        self.param = {}
        
        # 使用高精度的正则表达式提取字段，防止 Base64 编码中的 '+' 和 '=' 导致解析错乱
        def regex_find(key, src):
            match = re.search(rf'{key}\s*=\s*([^;]+)', src)
            return match.group(1).strip() if match else ''

        # 精准提取各个核心字段
        self.param['user'] = regex_find('user', cookie_str)
        self.param['kps'] = regex_find('kps', cookie_str)
        self.param['sign'] = regex_find('sign', cookie_str)
        self.param['vcode'] = regex_find('vcode', cookie_str)
        
        # 兼容备用格式：如果直接传入了带 url= 的特殊网页链接
        if 'url=' in cookie_str and not self.param['kps']:
            url_match = re.search(r'url=([^;&]+)', cookie_str)
            if url_match:
                url_str = url_match.group(1)
                self.param['kps'] = re.search(r'kps=([^&]+)', url_str).group(1) if 'kps=' in url_str else ''
                self.param['sign'] = re.search(r'sign=([^&]+)', url_str).group(1) if 'sign=' in url_str else ''
                self.param['vcode'] = re.search(r'vcode=([^&]+)', url_str).group(1) if 'vcode=' in url_str else ''

        # 设置账号别名
        self.user_alias = self.param.get('user') if self.param.get('user') else f"账号{self.index}"

    def convert_bytes(self, b):
        """将字节转换为 MB GB TB"""
        units = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
        i = 0
        while b >= 1024 and i < len(units) - 1:
            b /= 1024
            i += 1
        return f"{b:.2f} {units[i]}"

    def get_growth_info(self):
        """获取用户当前的签到信息"""
        url = "https://drive-m.quark.cn/1/clouddrive/capacity/growth/info"
        querystring = {
            "pr": "ucpro",
            "fr": "android",
            "kps": self.param.get('kps', ''),
            "sign": self.param.get('sign', ''),
            "vcode": self.param.get('vcode', '')
        }
        try:
            response = self.session.get(url=url, params=querystring, timeout=20).json()
            if response.get("data"):
                return response["data"]
        except Exception:
            pass
        return False

    def get_growth_sign(self):
        """执行签到请求"""
        url = "https://drive-m.quark.cn/1/clouddrive/capacity/growth/sign"
        querystring = {
            "pr": "ucpro",
            "fr": "android",
            "kps": self.param.get('kps', ''),
            "sign": self.param.get('sign', ''),
            "vcode": self.param.get('vcode', '')
        }
        data = {"sign_cyclic": True}
        try:
            response = self.session.post(url=url, json=data, params=querystring, timeout=30).json()
            if response.get("data"):
                return True, response["data"]["sign_daily_reward"]
            else:
                return False, response.get("message", "未知错误")
        except Exception as e:
            return False, str(e)

    def main(self):
        """主执行逻辑"""
        print(f"\n==== 夸克网盘账号{self.index} 开始签到 ====")
        
        if not self.param.get('kps') or not self.param.get('sign'):
            error_msg = "❌ 核心参数(kps/sign)缺失，请重新抓包核对。\n提示：当前解析到的参数键名有：" + str(list(self.param.keys()))
            print(error_msg)
            return error_msg, False

        # 1. 获取签到前信息
        growth_info = self.get_growth_info()
        if not growth_info:
            error_msg = "❌ 签到异常: 获取网盘成长信息失败，可能是参数失效或被防火墙拦截。"
            print(error_msg)
            return error_msg, False

        # 基础数据初始化
        user_type = '88VIP' if growth_info.get('88VIP') else '普通用户'
        total_cap = self.convert_bytes(growth_info.get('total_capacity', 0))
        
        sign_reward = 0
        if "sign_reward" in growth_info.get('cap_composition', {}):
            sign_reward = growth_info['cap_composition']['sign_reward']
        sign_reward_str = self.convert_bytes(sign_reward)

        # 2. 随机行为级等待
        time.sleep(random.uniform(2, 5))

        # 3. 校验并执行签到
        signin_success = False
        if growth_info.get("cap_sign", {}).get("sign_daily"):
            signin_success = True
            signin_msg = f"今日已签到 +{self.convert_bytes(growth_info['cap_sign']['sign_daily_reward'])}"
            progress_str = f"({growth_info['cap_sign']['sign_progress']}/{growth_info['cap_sign']['sign_target']})"
        else:
            success, sign_return = self.get_growth_sign()
            if success:
                signin_success = True
                signin_msg = f"签到成功 +{self.convert_bytes(sign_return)}"
                current_p = growth_info.get("cap_sign", {}).get("sign_progress", 0) + 1
                target_p = growth_info.get("cap_sign", {}).get("sign_target", 7)
                progress_str = f"({current_p}/{target_p})"
            else:
                signin_msg = f"签到失败: {sign_return}"
                progress_str = "(-/-)"

        # 4. 获取签到后信息完成容量跟踪
        time.sleep(random.uniform(1, 3))
        growth_info_after = self.get_growth_info()
        if growth_info_after:
            total_cap = self.convert_bytes(growth_info_after.get('total_capacity', 0))

        # 5. 组合最终展示报表
        final_msg = f"""🌟 夸克网盘签到结果

    👤 用户: {mask_username(self.user_alias)} [{user_type}]
    💾 网盘总容量: {total_cap}
    🎁 累计签到容量: {sign_reward_str}

    📝 签到状态: {signin_msg}
    🎯 连签进度: {progress_str}
    ⏰ 时间: {datetime.now().strftime('%m-%d %H:%M')}"""

        print(f"{'✅ 任务完成' if signin_success else '❌ 任务失败'}")
        return final_msg, signin_success

def main():
    """主程序入口"""
    print(f"==== 夸克网盘签到开始 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")
    print(f"🔒 隐私保护模式: {'已启用' if privacy_mode else '已禁用'}")

    # 全局大随机延迟
    if random_signin:
        delay_seconds = random.randint(0, max_random_delay)
        if delay_seconds > 0:
            print(f"🎲 随机延迟调谐: {format_time_remaining(delay_seconds)}")
            wait_with_countdown(delay_seconds, "夸克网盘签到")

    if not quark_cookie:
        error_msg = "❌ 未找到 QUARK_COOKIE 或 quark_cookie 环境变量，脚本退出。"
        print(error_msg)
        notify_user("夸克网盘签到失败", error_msg)
        return

    raw_cookies = parse_cookies(quark_cookie)
    if not raw_cookies:
        error_msg = "❌ quark_cookie 解析失败，格式有误。"
        print(error_msg)
        notify_user("夸克网盘签到失败", error_msg)
        return

    print(f"📝 共发现 {len(raw_cookies)} 个账号\n")

    success_count = 0
    total_count = len(raw_cookies)
    results = []

    for index, cookie_str in enumerate(raw_cookies):
        try:
            # 账号间串行混淆间歇
            if index > 0:
                delay = random.uniform(10, 20)
                print(f"⏱️  随机防关联等待 {delay:.1f} 秒后处理下一个账号...")
                time.sleep(delay)

            # 实例化执行器
            signer = QuarkSigner(cookie_str, index + 1)
            result_msg, is_success = signer.main()

            if is_success:
                success_count += 1

            results.append({
                'index': index + 1,
                'success': is_success,
                'message': result_msg,
                'username': mask_username(signer.user_alias)
            })

            # 发送单个账号通知
            status = "成功" if is_success else "失败"
            notify_user(f"夸克网盘账号{index + 1}签到{status}", result_msg)

        except Exception as e:
            error_msg = f"账号{index + 1}: 执行异常 - {str(e)}"
            print(f"❌ {error_msg}")
            notify_user(f"夸克网盘账号{index + 1}运行异常", error_msg)

    # 汇总通知
    if total_count > 1:
        summary_msg = f"""📊 夸克网盘签到汇总

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

        notify_user("夸克网盘签到汇总", summary_msg)

    print(f"\n==== 夸克网盘签到完成 - 成功{success_count}/{total_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ====")

def handler(event, context):
    """云函数兼容入口"""
    main()

if __name__ == "__main__":
    main()
