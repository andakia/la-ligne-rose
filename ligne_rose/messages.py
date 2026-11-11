"""Fixed voice-menu messages, in Wolof (`wo`) and French (`fr`).

These are the only sentences the line says on its own. Everything said during
a conversation comes from the Andakia Voice API. Each message is turned into
audio once through `/tts`, then cached (see `media.py`).

Wording is a working draft: it must be reviewed with native speakers and the
health partners before any public launch.
"""
from __future__ import annotations

LANGUAGES = ("wo", "fr")
DEFAULT_LANGUAGE = "wo"

MESSAGES: dict[str, dict[str, str]] = {
    "welcome": {
        "wo": "Dalal ak jàmm ci La Ligne Rose. Woote bi amul fay, te lépp dafa sutura.",
        "fr": "Bienvenue sur La Ligne Rose. Cet appel est gratuit et confidentiel.",
    },
    "choose_language": {
        "wo": "Ngir wolof, bësal benn.",
        "fr": "Pour le français, tapez deux.",
    },
    "main_menu": {
        "wo": (
            "Soo bëggee laaj ab laaj ci sa wér-gi-yaram, bësal benn. "
            "Soo bëggee wax ak ab fajkat walla ab sage-femme, bësal ñaar. "
            "Ngir dégluwaat, bësal juróom-ñeent."
        ),
        "fr": (
            "Pour poser une question sur votre santé, tapez un. "
            "Pour parler à une professionnelle de santé, tapez deux. "
            "Pour réécouter, tapez neuf."
        ),
    },
    "ai_intro": {
        "wo": "Laajal sa laaj ginnaaw bip bi. Saa yu la neexee, bësal zéro ngir wax ak ab fajkat.",
        "fr": "Posez votre question après le bip. À tout moment, tapez zéro pour parler à une professionnelle de santé.",
    },
    "not_understood": {
        "wo": "Déggu ma la bu baax. Waxaatal, su la neexee.",
        "fr": "Je ne vous ai pas bien entendue. Pouvez-vous répéter ?",
    },
    "invalid_choice": {
        "wo": "Tànn bi baaxul.",
        "fr": "Ce choix n'est pas valide.",
    },
    "transferring": {
        "wo": "Xaaral tuuti, maa ngi lay jokkale ak ab fajkat.",
        "fr": "Un instant, je vous mets en relation avec une professionnelle de santé.",
    },
    "human_unavailable": {
        "wo": "Fajkat yi amuñu jot léegi. Woowaatal ci kanam, walla bësal benn ngir laaj sa laaj.",
        "fr": "Aucune professionnelle n'est disponible pour le moment. Rappelez plus tard, ou tapez un pour poser votre question.",
    },
    "emergency": {
        "wo": "Bu dee lu jamp, woo secours yi léegi.",
        "fr": "S'il s'agit d'une urgence, appelez les secours immédiatement.",
    },
    "service_error": {
        "wo": "Am na jafe-jafe ci sunu wàll. Maa ngi lay jokkale ak ab fajkat.",
        "fr": "Nous rencontrons un problème technique. Je vous mets en relation avec une professionnelle de santé.",
    },
    "max_turns": {
        "wo": "Woote bi yàgg na. Ngir yeneen laaj, woowaatal walla wax ak ab fajkat.",
        "fr": "Cet appel arrive à sa fin. Pour d'autres questions, rappelez ou demandez une professionnelle de santé.",
    },
    "goodbye": {
        "wo": "Jërëjëf ci sa woote. Ba beneen yoon.",
        "fr": "Merci pour votre appel. À bientôt.",
    },
}


def text(key: str, language: str) -> str:
    entry = MESSAGES[key]
    return entry.get(language) or entry[DEFAULT_LANGUAGE]
