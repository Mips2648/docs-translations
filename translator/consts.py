EN_US = "en_US"
FR_FR = "fr_FR"
ES_ES = "es_ES"
DE_DE = "de_DE"
IT_IT = "it_IT"
PT_PT = "pt_PT"

ALL_LANGUAGES = [
    FR_FR,
    EN_US,
    ES_ES,
    DE_DE,
    IT_IT,
    PT_PT
]

LANGUAGES_TO_DEEPL = {
    FR_FR: 'FR',
    EN_US: 'EN-US',
    ES_ES: 'ES',
    DE_DE: 'DE',
    IT_IT: 'IT',
    PT_PT: 'PT-PT'
}

LANGUAGES_TO_DEEPL_GLOSSARY = {
    FR_FR: 'FR',
    EN_US: 'EN',
    ES_ES: 'ES',
    DE_DE: 'DE',
    IT_IT: 'IT',
    PT_PT: 'PT'
}

LOG_FORMAT = '[%(levelname)s] : %(message)s'

INPUT_SOURCE_LANGUAGE = 'source_language'
INPUT_TARGET_LANGUAGES = 'target_languages'
INPUT_DEEPL_API_KEY = 'deepl_api_key'
INPUT_DEBUG = 'debug'

DEFAULT_DOCS_ROOT = 'docs'
DEFAULT_MEMORY_SUB_PATH = '.translation_memory'
