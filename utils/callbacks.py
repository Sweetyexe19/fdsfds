"""Разбор callback_data вида prefix:id."""


def parse_callback_id(data: str, prefix: str) -> int:
    """
    prefix без двоеточия на конце, например 'adm:cat_new'.
    data: 'adm:cat_new:42' -> 42
    """
    head = f"{prefix}:"
    if not data.startswith(head):
        raise ValueError(f"Ожидался {head}, получено: {data}")
    suffix = data[len(head) :]
    if not suffix.isdigit():
        raise ValueError(f"Некорректный id в callback: {data}")
    return int(suffix)


def parse_callback_id_field(data: str, prefix: str) -> tuple[int, str]:
    """Например adm:edit:5:price -> (5, 'price')."""
    head = f"{prefix}:"
    if not data.startswith(head):
        raise ValueError(f"Ожидался {head}, получено: {data}")
    rest = data[len(head) :]
    cat_id_str, _, field = rest.partition(":")
    return int(cat_id_str), field
