import re
import hashlib
from typing import Dict, Any

class DataAnonymizer:
    # 1단계 방어: 정규표현식 (빠르고 확실한 패턴 차단)
    _DEIDENTIFY_PATTERNS = [
        (re.compile(r'01[016789]-?\d{3,4}-?\d{4}'), '[전화번호]'),
        (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '[이메일]'),
        (re.compile(r'\d{6}-[1-4]\d{6}'), '[주민번호]'),
        (re.compile(r'\d{2,3}-\d{3,4}-\d{4}'), '[유선전화]'), # 유선번호 추가
    ]

    @staticmethod
    def hash_user_id(user_id: int) -> str:
        """
        숫자형 user_id를 LLM이 유추할 수 없는 고유 해시 문자열로 변환합니다.
        예: 38 -> 'USER_a7b2'
        """
        # salt를 추가하여 보안을 높일 수 있습니다.
        salt = "moodtender_secret_salt"
        hashed = hashlib.sha256(f"{user_id}{salt}".encode()).hexdigest()[:6]
        return f"USER_{hashed.upper()}"

    @classmethod
    def clean_text_regex(cls, text: str) -> str:
        """
        사용자가 입력한 대화나 메모에서 명확한 개인정보 패턴을 1차로 지웁니다.
        (LLM deidentify_chain을 태우기 전, 안전장치 역할)
        """
        if not text:
            return ""
            
        cleaned_text = text
        for pattern, replacement in cls._DEIDENTIFY_PATTERNS:
            cleaned_text = pattern.sub(replacement, cleaned_text)
        return cleaned_text

    @staticmethod
    def mask_sensitive_apps(app_usage: Dict[str, int]) -> Dict[str, int]:
        """
        앱 사용 내역(JSON) 중 민감할 수 있는 앱을 블라인드 처리합니다.
        """
        if not app_usage:
            return {}

        safe_usage = app_usage.copy()
        
        # 금융, 의료, 데이팅, 보안 관련 앱 키워드
        sensitive_keywords = ['toss', 'bank', 'kb', '신한', 'tinder', 'glow', 'vpn', 'medical']
        
        hidden_time = 0
        keys_to_remove = []

        for app_name, time in safe_usage.items():
            app_name_lower = app_name.lower()
            if any(keyword in app_name_lower for keyword in sensitive_keywords):
                hidden_time += time
                keys_to_remove.append(app_name)

        # 원본에서 민감 앱 삭제
        for key in keys_to_remove:
            del safe_usage[key]

        # 삭제된 시간을 '기타_프라이빗_앱'으로 통합하여 총 스크린타임 오차 방지
        if hidden_time > 0:
            safe_usage['기타_프라이빗_앱'] = safe_usage.get('기타_프라이빗_앱', 0) + hidden_time

        return safe_usage

    @classmethod
    def prepare_safe_context(cls, user_id: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        1단계(analytics_service)에서 나온 결과를 LLM 프롬프트에 넣기 전,
        최종적으로 안전하게 포장하는 래퍼(Wrapper) 함수입니다.
        """
        safe_context = {
            "pseudo_id": cls.hash_user_id(user_id),
            "emotion": metrics['analysis']['emotion'],
            "deltas": metrics['deltas'],
            # 앱 내역이 있다면 마스킹 처리하여 포함
            "app_usage": cls.mask_sensitive_apps(metrics.get('today', {}).get('app_usage_json', {}))
        }
        return safe_context