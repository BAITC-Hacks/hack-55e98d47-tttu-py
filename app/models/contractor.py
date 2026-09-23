from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Contractor:
    id: str
    anon_name: str
    categories: tuple[str, ...]
    city: str
    price_from_kzt: int
    event_formats: tuple[str, ...]
    languages: tuple[str, ...]
    max_hours: int | None
    busy_dates: tuple[str, ...]
    description: str
    synthetic: bool
    city_imputed: bool
    price_imputed: bool

    def __post_init__(self):
        # Keep the same invariants at CSV import and SQLite deserialization boundaries.
        for value in (self.id, self.anon_name, self.city, self.description):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Contractor text fields must be nonempty strings")
        if self.city not in ("Алматы", "Астана", "Зарубежье"):
            raise ValueError("Unsupported contractor city")
        if type(self.price_from_kzt) is not int or self.price_from_kzt < 0:
            raise ValueError("Invalid contractor price")
        if self.max_hours is not None and (type(self.max_hours) is not int or self.max_hours <= 0):
            raise ValueError("Invalid contractor duration")
        if any(
            type(value) is not bool
            for value in (self.synthetic, self.city_imputed, self.price_imputed)
        ):
            raise ValueError("Contractor flags must be booleans")
        for values in (self.categories, self.event_formats, self.languages, self.busy_dates):
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() or value != value.strip()
                for value in values
            ):
                raise ValueError("Contractor lists must contain nonempty strings")
        if not self.categories or not self.event_formats or not self.languages:
            raise ValueError("Contractor service lists must not be empty")
        for day in self.busy_dates:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError("Invalid contractor busy date")
