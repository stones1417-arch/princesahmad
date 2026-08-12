from __future__ import annotations

import re


class InvalidRecipientError(Exception):
    pass


class RecipientResolver:
    SAUDI_MOBILE = re.compile(r"^05\d{8}$")
    SAUDI_MOBILE_WITHOUT_ZERO = re.compile(r"^5\d{8}$")
    E164 = re.compile(r"^\+[1-9]\d{7,14}$")

    def resolve(self, employee, channel: str) -> str:
        if channel in {"sms", "whatsapp"}:
            return self._phone(employee.phone_number)
        if channel == "email":
            if not employee.email:
                raise InvalidRecipientError("لا يوجد بريد إلكتروني مسجل للموظف.")
            return employee.email.strip()
        raise InvalidRecipientError("قناة الاتصال غير مدعومة.")

    def _phone(self, value: str) -> str:
        number = re.sub(r"[\s\-()]", "", value or "")
        if self.SAUDI_MOBILE.fullmatch(number):
            return "+966" + number[1:]
        if self.SAUDI_MOBILE_WITHOUT_ZERO.fullmatch(number):
            return "+966" + number
        if self.E164.fullmatch(number):
            return number
        raise InvalidRecipientError("رقم الجوال غير صالح. استخدم صيغة E.164 أو 05xxxxxxxx.")

    @staticmethod
    def mask(address: str) -> str:
        if address.startswith("+") and len(address) > 7:
            return f"{address[:5]}*****{address[-3:]}"
        return address