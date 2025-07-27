def normalize_language_input(raw):
    mapping = {
        'english': 'en', 'german': 'de', 'spanish': 'es', 'swedish': 'se',
        'norwegian': 'no', 'russian': 'ru', 'ukrainian': 'ua', 'italian': 'it',
        'new zealand': 'nz', 'dutch': 'nl', 'mexican': 'mx', 'portuguese': 'pt',
        'brazilian': 'br', 'australian': 'au', 'canadian': 'ca', 'costa rican': 'cr',
        'danish': 'dk', 'irish': 'ie', 'icelandic': 'is', 'thai': 'th', 'french': 'fr',
        'greek': 'gr', 'polish': 'pl', 'finnish': 'fi', 'hong kong': 'hk',
        'argentinian': 'ar', 'turkish': 'tr', 'korean': 'kr', 'japanese': 'jp',
        'chinese': 'cn', 'indian': 'in'
    }

    valid_langs = []
    invalid_langs = []

    for lang in raw.split(','):
        lang_clean = lang.strip().lower()
        code = mapping.get(lang_clean)

        if code:
            valid_langs.append(code)
        else:
            invalid_langs.append(lang_clean)

    if invalid_langs:
        raise ValueError(f"Unsupported languages: {', '.join(invalid_langs)}")

    return ','.join(valid_langs)
