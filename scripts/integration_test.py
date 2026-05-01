"""Integration test script for the video editing API"""

import sys
import asyncio
from pathlib import Path
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from src.db import SessionLocal, init_db
from src.models import Project, Session as DBSession, VideoJob
from src.core.discussion_engine import discussion_engine


def test_project_creation():
    """Test creating a project"""
    print("\n🧪 Testing project creation...")
    db = SessionLocal()
    try:
        project = Project(
            name="Test Project",
            description="A test creative project",
            metadata_={},
        )
        db.add(project)
        db.commit()
        print(f"✅ Created project: {project.id} - {project.name}")
        return project.id
    finally:
        db.close()


def test_session_creation(project_id):
    """Test creating a session"""
    print("\n🧪 Testing session creation...")
    db = SessionLocal()
    try:
        session = DBSession(
            project_id=project_id,
            prompt="Create a warm healing version of the story with hope",
            style_preference="warmHealing",
            status="active",
            discussion_history=[],
            script="",
        )
        db.add(session)
        db.commit()
        print(f"✅ Created session: {session.id}")
        return session.id
    finally:
        db.close()


def test_discussion_generation(prompt, style):
    """Test discussion timeline generation"""
    print(f"\n🧪 Testing discussion generation...")
    print(f"   Prompt: {prompt}")
    print(f"   Style: {style}")

    try:
        turns, script = discussion_engine.generate_timeline(prompt, style)
        print(f"✅ Generated {len(turns)} discussion turns")
        print(f"✅ Generated script ({len(script)} chars)")

        # Print first few turns
        print("\nFirst few discussion turns:")
        for i, turn in enumerate(turns[:5]):
            print(f"  {i+1}. [{turn.stage}] {turn.speaker} ({turn.role}): {turn.content[:50]}...")

        print("\n📄 Script preview:")
        script_lines = script.split("\n")[:10]
        for line in script_lines:
            print(f"  {line}")

        return turns, script
    except Exception as e:
        print(f"❌ Discussion generation failed: {e}")
        raise


def test_video_job_creation(session_id):
    """Test creating a video job"""
    print("\n🧪 Testing video job creation...")
    db = SessionLocal()
    try:
        job = VideoJob(
            session_id=session_id,
            phase="collect",
            status="pending",
            script="",
            output_path=None,
        )
        db.add(job)
        db.commit()
        print(f"✅ Created video job: {job.id}")
        print(f"   Phase: {job.phase}, Status: {job.status}")
        return job.id
    finally:
        db.close()


def test_director_profiles():
    """Test director profile loading"""
    print("\n🧪 Testing director profile loading...")

    guardians = discussion_engine.profiles.get_guardians()
    directors = discussion_engine.profiles.get_directors()

    print(f"✅ Loaded {len(guardians)} guardians:")
    for g in guardians:
        print(f"   - {g['name']}: {g['stance']}")

    print(f"✅ Loaded {len(directors)} directors:")
    for d in directors:
        print(f"   - {d['name']}: {d['stance']}")

    # Test panel selection
    print("\n🧪 Testing panel selection by style:")
    for style in ["warmHealing", "darkEpic", "auto"]:
        panel = discussion_engine.profiles.select_panel_members(style)
        print(f"  {style}: {len(panel['guardians'])} guardians + {len(panel['directors'])} directors")


def main():
    """Run all integration tests"""
    print("=" * 60)
    print("🚀 Video Editing API Integration Tests")
    print("=" * 60)

    try:
        # Test director profiles
        test_director_profiles()

        # Test discussion generation with different styles
        test_discussion_generation(
            "Adapt the story with hope and healing",
            "warmHealing",
        )

        test_discussion_generation(
            "Create a dark epic version with high stakes",
            "darkEpic",
        )

        # Test database operations
        project_id = test_project_creation()
        session_id = test_session_creation(project_id)
        job_id = test_video_job_creation(session_id)

        # Test updating session with discussion
        print("\n🧪 Testing session update with discussion...")
        db = SessionLocal()
        try:
            session = db.query(DBSession).filter(DBSession.id == session_id).first()
            turns, script = discussion_engine.generate_timeline(
                session.prompt,
                session.style_preference,
            )
            session.discussion_history = [turn.dict() for turn in turns]
            session.script = script
            db.commit()
            print(f"✅ Updated session with discussion history and script")
        finally:
            db.close()

        print("\n" + "=" * 60)
        print("✅ All integration tests passed!")
        print("=" * 60)
        print("\n📌 Summary:")
        print(f"  • Created project: {project_id}")
        print(f"  • Created session: {session_id}")
        print(f"  • Created video job: {job_id}")
        print(f"  • Generated discussions with multiple styles")
        print(f"  • All database operations successful")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
