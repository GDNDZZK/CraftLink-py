from core import data


class CraftLinkModsMain:
    class modsInfo:
        GDNDZZK = "CraftLink"
        version = "api_v1"
        name = "demo"

    def craftLinkEvent(self, evt: data):
        if evt.t == "craftLinkInit":
            self.data["count"] = self.data.get("count", 0) + 1
            self.data["info"] = {"name": "demo", "tags": {"a", "b"}, "points": (1, 2.5)}
            self.logger.info(f"第 {self.data['count']} 次启动, 后端: {self.data.backend}")
            return
        self.logger.info(f"t={evt.t} d={evt.d} info={self.data.get('info')}")
