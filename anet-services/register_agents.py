from __future__ import annotations

from anet.svc import SvcClient


AGENTS = [
    {"name": "yinanping-composer", "port": 7101, "tags": ["composer", "music", "film"]},
    {"name": "yinanping-editor", "port": 7102, "tags": ["editor", "film"]},
    {"name": "yinanping-director", "port": 7103, "tags": ["director", "story"]},
    {"name": "yinanping-collector", "port": 7104, "tags": ["collector", "research"]},
]


def main() -> None:
    with SvcClient() as svc:
        for agent in AGENTS:
            svc.register(
                name=agent["name"],
                endpoint=f"http://127.0.0.1:{agent['port']}",
                paths=["/generate", "/health"],
                modes=["rr"],
                free=True,
                tags=agent["tags"],
            )
            print(f"[ok] registered {agent['name']}")


if __name__ == "__main__":
    main()
