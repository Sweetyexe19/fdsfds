MAX_CATEGORY_DEPTH = 2  # 0=категория, 1=подкатегория, 2=подподкатегория


def level_name(depth: int) -> str:
    return ("категорию", "подкатегорию", "подподкатегорию")[min(depth, 2)]


def add_child_button_label(parent_depth: int, *, more: bool = False) -> str:
    """Подпись кнопки добавления дочернего раздела."""
    names = ("Подкатегория", "Подподкатегория", "Раздел")
    name = names[min(parent_depth, 2)]
    prefix = "➕ Ещё " if more else "➕ "
    return f"{prefix}{name}"


def format_catalog_button(name: str, *, is_leaf: bool, price: float, count: int) -> str:
    if is_leaf and price > 0:
        return f"{name} — {price:.0f}₽ ({count} шт.)"
    if is_leaf:
        return f"{name} ({count} шт.)"
    return f"{name} →"
