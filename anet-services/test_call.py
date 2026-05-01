from __future__ import annotations

from anet.svc import SvcClient


def main() -> None:
    with SvcClient() as svc:
        peers = svc.discover(skill="composer")
        print("discovered:", [peer.get("name", "") for peer in peers])
        if not peers:
            raise RuntimeError("no composer peers discovered")

        target = peers[0]
        response = svc.call(
            target["peer_id"],
            target["name"],
            "/generate",
            method="POST",
            body={
                "topic": "Harry Potter",
                "scene": "final reunion",
                "style": "warmHealing",
            },
        )
        body = response.get("body", {}) if isinstance(response, dict) else {}
        result = str(body.get("result", ""))
        print("result:", result[:160])


if __name__ == "__main__":
    main()
