"""CommentaryBooth - two voices in the booth.

For every aired moment, the lead commentator calls the action and the co-commentator
explains why it mattered. Lead lines are short exclamations with names only, no figures.
Every number the co-commentator says is a line the FactChecker has already verified, so the
booth can never say something the match data does not support.

Output, per language:  [{"who": "lead", "text": ...}, {"who": "analyst", "text": ...}]
"""
from __future__ import annotations

from typing import Optional

CALLS = {
    "en": {
        "goal": ["{p}! It's in! {team} score!", "Oh, {p}! What a finish!", "{p} buries it! Get in!"],
        "hat_trick": ["Hat-trick! {p} has three!"], "brace": ["That's two for {p}!"],
        "chance_saved": ["{p} shoots... and it's saved!", "Big chance for {p}... kept out!"],
        "chance_missed": ["{p} lets fly... just wide!", "{p} has to score... and he doesn't!"],
        "chance_blocked": ["{p} shoots, and it's blocked!"],
        "line_break": ["{p} threads it through!", "Lovely ball from {p}!"], "hard_pass": ["{p} finds a way through!"],
        "sprint": ["{p} is away!"], "long_carry": ["{p} drives forward!"],
        "card_yellow": ["That's a yellow card for {p}."], "card_red": ["And that's red! {p} is off!"],
        "momentum": ["{team} are turning the screw here."], "phase": ["Look at the pattern of this game now."],
        "press": ["{team} are hunting in packs!"], "wp_swing": ["That changes everything for {team}."],
        "saves": ["Another stop! {p} is having a night!"], "standout": ["{p} has been everywhere tonight."],
        "story_duel": ["These two again!"], "story_channel": ["Same route again for {team}."], "story_keeper": ["The keeper is earning his money."],
        "story_waste": ["Possession given away again."], "story_fatigue": ["Tired legs out there now."],
        "half_time": ["There's the half-time whistle."], "full_time": ["And that's full time!"],
        "_": ["Here's {p} again."],
    },
    "es": {
        "goal": ["¡{p}! ¡Gol! ¡Marca {team}!", "¡Qué definición de {p}!"], "hat_trick": ["¡Triplete! ¡{p} hace tres!"], "brace": ["¡Doblete de {p}!"],
        "chance_saved": ["¡Dispara {p}... y la para el portero!"], "chance_missed": ["¡{p} remata... fuera por poco!"],
        "chance_blocked": ["¡Dispara {p} y la bloquean!"], "line_break": ["¡Qué pase de {p}!"], "hard_pass": ["¡{p} encuentra el hueco!"],
        "sprint": ["¡Se va {p}!"], "long_carry": ["¡Conduce {p} hacia arriba!"],
        "card_yellow": ["Tarjeta amarilla para {p}."], "card_red": ["¡Roja! ¡{p} se va a la calle!"],
        "momentum": ["{team} aprieta ahora."], "phase": ["Mira cómo ha cambiado el partido."], "press": ["¡{team} presiona arriba!"],
        "wp_swing": ["Eso lo cambia todo para {team}."], "saves": ["¡Otra parada! ¡Qué noche de {p}!"], "standout": ["{p} está en todas partes."],
        "story_duel": ["¡Otra vez estos dos!"], "story_channel": ["Otra vez por la misma banda."], "story_keeper": ["El portero se lo está ganando."],
        "story_waste": ["Otra pérdida de balón."], "story_fatigue": ["Ya pesan las piernas."],
        "half_time": ["Final de la primera parte."], "full_time": ["¡Final del partido!"], "_": ["Otra vez {p}."],
    },
    "fr": {
        "goal": ["{p} ! But ! {team} marque !", "Quelle finition de {p} !"], "hat_trick": ["Triplé ! {p} en met trois !"], "brace": ["Doublé pour {p} !"],
        "chance_saved": ["{p} frappe... arrêté !"], "chance_missed": ["{p} tente... juste à côté !"], "chance_blocked": ["{p} frappe, et c'est contré !"],
        "line_break": ["Quel ballon de {p} !"], "hard_pass": ["{p} trouve la faille !"], "sprint": ["{p} s'en va !"], "long_carry": ["{p} avance balle au pied !"],
        "card_yellow": ["Carton jaune pour {p}."], "card_red": ["Rouge ! {p} est exclu !"],
        "momentum": ["{team} met la pression."], "phase": ["Regardez comme le match a changé."], "press": ["{team} presse très haut !"],
        "wp_swing": ["Ça change tout pour {team}."], "saves": ["Encore un arrêt ! Quelle soirée pour {p} !"], "standout": ["{p} est partout ce soir."],
        "story_duel": ["Encore ces deux-là !"], "story_channel": ["Toujours le même couloir."], "story_keeper": ["Le gardien fait le travail."],
        "story_waste": ["Encore un ballon perdu."], "story_fatigue": ["Les jambes sont lourdes."],
        "half_time": ["C'est la mi-temps."], "full_time": ["C'est terminé !"], "_": ["Encore {p}."],
    },
    "pt": {
        "goal": ["{p}! Golo! Marca o {team}!", "Que finalização de {p}!"], "hat_trick": ["Hat-trick! {p} faz três!"], "brace": ["Bis de {p}!"],
        "chance_saved": ["{p} remata... e o guarda-redes defende!"], "chance_missed": ["{p} remata... ao lado!"], "chance_blocked": ["{p} remata e é bloqueado!"],
        "line_break": ["Que passe de {p}!"], "hard_pass": ["{p} encontra o espaço!"], "sprint": ["{p} vai embora!"], "long_carry": ["{p} conduz para a frente!"],
        "card_yellow": ["Cartão amarelo para {p}."], "card_red": ["Vermelho! {p} está expulso!"],
        "momentum": ["O {team} está a apertar."], "phase": ["Veja como o jogo mudou."], "press": ["O {team} pressiona alto!"],
        "wp_swing": ["Isso muda tudo para o {team}."], "saves": ["Mais uma defesa! Que noite de {p}!"], "standout": ["{p} está em todo o lado."],
        "story_duel": ["Outra vez estes dois!"], "story_channel": ["Outra vez pelo mesmo corredor."], "story_keeper": ["O guarda-redes está a trabalhar."],
        "story_waste": ["Mais uma perda de bola."], "story_fatigue": ["As pernas já pesam."],
        "half_time": ["Intervalo."], "full_time": ["Fim do jogo!"], "_": ["Outra vez {p}."],
    },
}
NO_PLAYER = {"momentum", "phase", "press", "wp_swing", "story_channel", "story_waste", "story_fatigue", "half_time", "full_time", "story_duel", "story_keeper"}


class CommentaryBooth:
    name = "CommentaryBooth"
    role = "Two-voice commentary: a lead call plus a verified co-commentary line"

    def __init__(self, players: dict, teams: dict) -> None:
        self.players = players      # pid -> Player
        self.teams = teams          # side -> team name
        self.n = 0

    def _player(self, ins: dict) -> Optional[str]:
        pid = ins.get("player_id") or (ins.get("viz") or {}).get("player_id")
        p = self.players.get(pid) if pid else None
        return p.name.split(" ")[-1] if p else None

    def exchange(self, ins: dict) -> dict:
        kind, out = ins["kind"], {}
        p, team = self._player(ins), self.teams.get(ins.get("team") or "", "")
        self.n += 1
        for lang, calls in CALLS.items():
            opts = calls.get(kind) or calls["_"]
            line = opts[self.n % len(opts)]
            if ("{p}" in line and not p) or ("{team}" in line and not team):
                line = next((o for o in opts if ("{p}" not in o or p) and ("{team}" not in o or team)), "")
            lead = line.format(p=p or "", team=team).strip()
            r = ((ins.get("renders") or {}).get("casual") or {}).get(lang)
            reply = None
            if r and r.get("lines"):
                story = [l for l in r["lines"] if (l.get("k") or "").startswith("s.")]
                reply = (story[-1] if story else r["lines"][0])["text"]
            ex = ([{"who": "lead", "text": lead}] if lead else []) + ([{"who": "analyst", "text": reply}] if reply else [])
            if ex:
                out[lang] = ex
        return out
