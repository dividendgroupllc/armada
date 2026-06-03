__version__ = "0.0.1"

# Standart "Gross Profit" reportini (Customer bo'yicha group) kengaytiramiz.
# erpnext yadrosiga tegmasdan, ish vaqtida execute'ni o'raydi.
from armada.overrides import gross_profit as _armada_gross_profit  # noqa: E402

_armada_gross_profit.apply()
