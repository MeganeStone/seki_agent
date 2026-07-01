import time
import re
import os
from openai import OpenAI
from openai import APIError, RateLimitError, APITimeoutError, APIConnectionError
from langchain_core.tools import ToolException
# 新增：导入httpx处理客户端配置
import httpx
from dotenv import load_dotenv
load_dotenv()

# ---------------------- 全局配置（你的默认目录） ----------------------
DEFAULT_TARGET_LANG = os.getenv("TRANSLATE_TARGET_LANG") or "日语"  # 默认翻译目标语言
DEFAULT_DELAY = os.getenv("TRANSLATE_DELAY") or 1.2  # 每次翻译后的延迟，单位秒（可调整，过快可能触发API限速）
MAX_CONTEXT_LENGTH = 2000  # 上下文最大长度（防止Token超限）
TRANSLATE_LLM_MODEL = os.getenv("TRANSLATE_LLM_MODEL") or "qwen-plus"
TRANSLATE_BASE_URL = os.getenv("TRANSLATE_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
TRANSLATE_API_KEY = os.getenv("TRANSLATE_API_KEY")

# 全局客户端
_client = None
_translation_cache = {}


def _looks_already_japanese(text: str) -> bool:
    """
    判断一段文本是否"已经是日语、无需再翻译"。

    修复要点（原 bug）：
      旧逻辑 `re.search(r"[\u3040-\u30ff]", text)` 只要出现该范围内任意字符就跳过，
      但该范围包含当标点用的 ・(U+30FB 中点) 和 ー(U+30FC 长音符)，
      导致「・USB升级...」这类以中点起头、实则全是中文的段落被整段跳过 → 漏翻。

    新逻辑（偏向"宁可重译，不可漏翻"）：
      1. 只要文本仍含 CJK 汉字，就无法可靠区分中/日，一律送去翻译（返回 False）；
         代价是已是日语的汉字句会被重译一次（temperature 低时基本原样返回，安全）。
      2. 不含汉字、但含"真正的"平假名/片假名（排除 ・ ー 等标点）时，
         才认定已是日语并跳过。
    """
    if re.search(r"[\u4e00-\u9fff]", text):
        return False
    # 真正的假名：平假名 U+3041-3096、片假名 U+30A1-30FA（刻意排除 ・U+30FB、ー U+30FC 等）
    return bool(re.search(r"[\u3041-\u3096\u30a1-\u30fa]", text))


def _is_valid_translation(translation: str | None, target_lang: str) -> bool:
    if not translation or not translation.strip():
        return False
    if target_lang == "日语":
        return bool(re.search(r"[\u3040-\u30ff\u31f0-\u31ff\u4e00-\u9fffA-Za-z0-9]", translation))
    return True

def _create_client(api_key: str):
    """获取OpenAI客户端（适配DashScope兼容模式）"""
    base_url = TRANSLATE_BASE_URL
    http_client = httpx.Client(
        timeout=httpx.Timeout(10.0, connect=20.0),  # 显式设置超时
        follow_redirects=True,
    )
    _client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
    return _client

def translate_text(text: str, target_lang: str = DEFAULT_TARGET_LANG, delay: float = DEFAULT_DELAY, 
                   context: dict = None) -> str:
    """
    翻译文本，支持上下文参考和重试机制
    :param text: 要翻译的文本
    :param target_lang: 目标语言（默认日语）
    :param delay: 翻译延迟（默认1.2秒）
    :param context: 上下文信息
    :return: 翻译结果
    """
    api_key = os.environ.get("TRANSLATE_API_KEY")  # 由上层工具设置
    if not api_key:
        raise ToolException("TRANSLATE_API_KEY is not configured")
    # 初始化默认上下文
    context = context or {
        "file_name": "未知文件",
        "slide_num": 0,
        "total_slides": 0,
        "translated_segments": [],
        "term_requirements": "汽车行业术语（如TBOX/TSU/CAN总线）需统一翻译，公司名称不翻译"
    }
    if not text or not isinstance(text, str) or text.strip() == "":
        return text
    # 基础过滤
    text = re.sub(r"请提供需要翻译的原文内容.*", "", text)
    # 修复：不再"只要含假名就跳过"，改为更稳健的判断（详见 _looks_already_japanese）
    if target_lang == "日语" and _looks_already_japanese(text):
        return text
    company_names = (
        "上海畅星", "上海暢星",
        "上海畅星软件有限公司", "上海暢星軟件有限公司",
        "上海畅星软件有限会社", "上海暢星ソフトウェア有限公司"
    )
    for name in company_names:
        if name in text:
            return text
    # if not re.search(r"[\u4e00-\u9fff]", text):
    #     return text
    
    # 缓存key加入上下文标识（保证同文件同页的缓存隔离）
    cache_key = f"{context['file_name']}_{context['slide_num']}_{text}_{target_lang}"
    if cache_key in _translation_cache:
        print(f"[缓存命中] 页码{context['slide_num']} | 文本长度: {len(text)}")
        return _translation_cache[cache_key]

    print(f"\n[开始翻译] 文本长度: {len(text)} | 目标语言: {target_lang}")

    # ====================== 核心修改：构建带上下文的Prompt ======================
    # 拼接已翻译的上下文（只保留最近的，控制长度）
    # translated_context = "\n".join(context["translated_segments"][-3:])  # 只保留最近3段 todo：token充裕时可增加上下文数量，提升连贯性，但要注意Token限制
    translated_context = '暂无已翻译段落'  # 当前token限制较紧，暂时关闭上下文传递，后续可根据实际情况调整是否开启上下文参考
    # 截断上下文，防止Token超限
    if len(translated_context) > MAX_CONTEXT_LENGTH:
        translated_context = translated_context[-MAX_CONTEXT_LENGTH:]

    # 带上下文的系统提示
    system_prompt = f"""
    你是汽车TSU(本公司开发的产品，Telematic Systems Unit)专业翻译官，需遵守以下规则：
    1. 翻译目标：将文本内容翻译成{target_lang}，数字保持不变；
    2. 上下文参考：本次翻译属于文件「{context['file_name']}」的第{context['slide_num']}页（共{context['total_slides']}页）；
    3. 连贯要求：需参考当前页已翻译的段落保持术语、语气、格式统一：
       {translated_context if translated_context else '暂无已翻译段落'}
    4. 术语要求：{context['term_requirements']}；
    5. 格式要求：保留原文中的换行、编号、项目符号（如「・」）、括号等结构，仅翻译文字内容；
    6. 输出要求：只输出翻译结果，无任何解释、说明或额外文字。
    """
    
    # 用户提示：明确待翻译文本
    user_prompt = f"请翻译以下内容：\n{text}"
    
    translation = None
    # 重试策略
    for attempt in range(2):
        try:
            client = _create_client(api_key=api_key)
            # 修正：使用正确的OpenAI调用方法（chat.completions.create）
            resp = client.chat.completions.create(
                model=TRANSLATE_LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1
            )
            translation = resp.choices[0].message.content.strip()
            # 过滤额外输出
            translation = re.sub(r"^[\s\u3000]*翻译结果：|^[\s\u3000]*译文：", "", translation)
            if _is_valid_translation(translation, target_lang):
                print(f"[翻译成功] 尝试{attempt+1}次，结果长度: {len(translation)}")
                # 更新上下文：将本次翻译结果加入已翻译段落（供后续段落参考）
                context["translated_segments"].append(f"原文：{text} | 译文：{translation}")
                break
            else:
                print(f"[翻译无效] 尝试{attempt+1}次，结果无{target_lang}内容，重试...")
                translation = None
        except (APIError, RateLimitError, APITimeoutError, APIConnectionError) as e:
            print(f"[重试] 尝试{attempt+1}次失败（API错误）: {e}")
            time.sleep(delay * (attempt + 1))
        except Exception as e:
            print(f"[重试] 尝试{attempt+1}次失败（其他错误）: {e}")
            time.sleep(delay * (attempt + 1))

    # 兜底
    if not translation or translation.strip() == "":
        raise ToolException("翻译失败：模型未返回有效译文，请检查 TRANSLATE_API_KEY 和模型配置")
    else:
        time.sleep(delay)

    # 缓存翻译结果
    _translation_cache[cache_key] = translation
    return translation
