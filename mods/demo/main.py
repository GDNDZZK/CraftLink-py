from core import data


class CraftLinkModsMain:
    class modsInfo:
        GDNDZZK = "CraftLink"
        version = "api_v1"
        name = "demo"

    def craftLinkEvent(self, evt: data):
        self.logger.info(f"t={evt.t} d={evt.d}")
