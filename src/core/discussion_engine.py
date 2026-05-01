"""Discussion engine for creative collaboration"""

import json
import logging
import random
from datetime import datetime
from typing import List, Dict, Any

import yaml

from src.schemas import DiscussionTurn
from src.config import settings

logger = logging.getLogger(__name__)


class DirectorProfiles:
    """Manager for director and guardian profiles"""

    def __init__(self, config_path: str = "config/directors.yaml"):
        self.config_path = config_path
        self._load_config()

    def _load_config(self):
        """Load director config from YAML"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f)
                logger.info(f"✅ Loaded directors config from {self.config_path}")
        except Exception as e:
            logger.error(f"❌ Failed to load directors config: {e}")
            self.config = {}

    def get_guardians(self) -> List[Dict[str, Any]]:
        """Get all guardians"""
        return self.config.get("guardians", [])

    def get_directors(self) -> List[Dict[str, Any]]:
        """Get all directors"""
        return self.config.get("directors", [])

    def get_panel_for_style(self, style: str) -> Dict[str, List[str]]:
        """Get panel (guardians + directors) for given style"""
        style_panels = self.config.get("style_panels", {})
        return style_panels.get(style, style_panels.get("auto", {}))

    def select_panel_members(self, style: str) -> Dict[str, Any]:
        """Select panel members based on style preference"""
        panel_config = self.get_panel_for_style(style)
        guardians = self.get_guardians()
        directors = self.get_directors()

        selected = {
            "guardians": [],
            "directors": [],
            "style": style,
            "description": panel_config.get("description", ""),
        }

        # Select guardians
        guardian_ids = panel_config.get("guardians", [])
        for g_id in guardian_ids:
            g = next((g for g in guardians if g["id"] == g_id), None)
            if g:
                selected["guardians"].append(g)

        # Select directors
        director_ids = panel_config.get("directors", [])
        for d_id in director_ids:
            d = next((d for d in directors if d["id"] == d_id), None)
            if d:
                selected["directors"].append(d)

        return selected


class DiscussionEngine:
    """Generate discussion timeline for creative sessions"""

    def __init__(self, profiles: DirectorProfiles):
        self.profiles = profiles
        self._load_templates()

    def _load_templates(self):
        """Load dialogue templates from config"""
        config = self.profiles.config
        self.templates = config.get("dialogue_templates", {})
        self.topics = config.get("topics", [])

    def generate_timeline(self, session_prompt: str, style: str) -> tuple[List[DiscussionTurn], str]:
        """
        Generate discussion timeline and markdown script for a session

        Returns:
            Tuple of (discussion_turns, markdown_script)
        """
        # Select panel
        panel = self.profiles.select_panel_members(style)
        all_members = panel["guardians"] + panel["directors"]

        turns: List[DiscussionTurn] = []
        script_parts = []

        # System event: briefing
        ts = int(datetime.now().timestamp() * 1000)
        turns.append(
            DiscussionTurn(
                speaker="系统",
                role="system",
                content=f"创意讨论启动：{session_prompt}",
                stage="briefing",
                ts=ts,
            )
        )

        script_parts.append(f"# 创意制作脚本\n\n**主题**: {session_prompt}\n**风格**: {style}\n\n")

        # Generate three topics
        discussion_stages = [
            ("topic-1", "原著底线", "preservation"),
            ("topic-2", "情绪曲线", "emotional"),
            ("topic-3", "镜头执行", "technical"),
        ]

        script_parts.append("## 讨论过程\n\n")

        for stage, topic_name, template_key in discussion_stages:
            ts += 2000

            # Topic introduction
            turns.append(
                DiscussionTurn(
                    speaker="主持",
                    role="system",
                    content=f"议题：{topic_name}",
                    stage=stage,
                    ts=ts,
                )
            )

            script_parts.append(f"### {topic_name}\n\n")

            # Generate discussion turns for this topic
            for i, member in enumerate(all_members):
                ts += 3000
                speaker_name = member.get("name", "未知")

                # Get template for this member and topic
                template = self._get_dialogue_template(template_key, member.get("role_type"))

                if template:
                    content = template
                else:
                    # Fallback to simple response
                    content = f"我认为在 {topic_name} 上，应该 {member.get('stance', '有所考虑')}。"

                turn = DiscussionTurn(
                    speaker=speaker_name,
                    role=member.get("role_type", "crew"),
                    content=content,
                    stage=stage,
                    ts=ts,
                )
                turns.append(turn)

                # Add to script
                script_parts.append(f"**{speaker_name}** ({member.get('role_type', 'crew')}): {content}\n\n")

        # Finalize
        ts += 2000
        turns.append(
            DiscussionTurn(
                speaker="主持",
                role="system",
                content="讨论总结：根据以上建议，制作方案已生成",
                stage="finalize",
                ts=ts,
            )
        )

        script_parts.append("## 制作建议总结\n\n")
        script_parts.append("基于以上讨论，建议的制作方向为：\n\n")
        script_parts.append("1. 原著保留：保持核心人物关系和主题设定\n")
        script_parts.append("2. 情绪承载：通过视听效果强化代价感和救赎意义\n")
        script_parts.append("3. 执行方案：采用克制而有力的镜头语言\n\n")

        script_parts.append("---\n*本脚本由多智能体讨论生成*\n")

        markdown_script = "".join(script_parts)

        return turns, markdown_script

    def _get_dialogue_template(self, template_key: str, role_type: str) -> str:
        """Get dialogue template for given topic and role"""
        template_group = self.templates.get(template_key, [])
        matching_templates = [t for t in template_group if t.get("role") == role_type]

        if matching_templates:
            template = random.choice(matching_templates).get("template", "")
            # Basic variable substitution (can be enhanced)
            template = template.replace("{element}", "关键要素")
            template = template.replace("{approach}", "创意转化")
            template = template.replace("{character}", "主角")
            template = template.replace("{sacrifice}", "牺牲")
            template = template.replace("{method}", "视听手段")
            template = template.replace("{medium}", "视频语言")
            template = template.replace("{shot_type}", "长镜头")
            template = template.replace("{moment}", "高潮时刻")
            template = template.replace("{technique}", "音效设计")
            return template

        return ""


# Global instance
director_profiles = DirectorProfiles("config/directors.yaml")
discussion_engine = DiscussionEngine(director_profiles)
