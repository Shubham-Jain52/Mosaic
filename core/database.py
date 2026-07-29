"""Save scraped PR and comment data locally with SQLAlchemy.

v1 is single-repo: owner/repo live in .env. Connecting a different repo
requires a fresh mosaic.db (or a later multi-repo migration).
Duplicates are handled by composite PK (comment_type, comment_id) + merge().
"""

# pyrefly: ignore [missing-import]
from typing import List, Optional

from sqlalchemy import create_engine, ForeignKey, Text, String, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, relationship

from .models import PR_Structure

DB_URL = "sqlite:///mosaic.db"
engine = create_engine(DB_URL, echo=False)
session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class PULL_REQUEST(Base):
    __tablename__ = "pull_requests"
    number: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    state: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    comments: Mapped[List["comments_table"]] = relationship(
        "comments_table", back_populates="pr_relationship"
    )


class comments_table(Base):
    __tablename__ = "comment_table"
    # Composite PK: GitHub ids are not guaranteed unique across comment kinds.
    comment_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    comment_id: Mapped[int] = mapped_column(primary_key=True)
    pr_number: Mapped[int] = mapped_column(ForeignKey("pull_requests.number"), nullable=False)
    comment_body: Mapped[str] = mapped_column(Text)
    diff_hunk: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(255))
    review_state: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    pr_relationship = relationship("PULL_REQUEST", back_populates="comments")


def save_data_to_db(prs: List[PR_Structure]) -> None:
    """Upsert a list of PRs and all of their labeled comments into SQLite."""
    db = session_local()
    try:
        for pr_data in prs:
            pr_obj = PULL_REQUEST(
                number=pr_data.number,
                title=pr_data.title or "",
                state=pr_data.state or "",
                description=pr_data.description,
            )
            db.merge(pr_obj)

            for comment_data in pr_data.comments:
                if comment_data.comment_id is None or not comment_data.comment_type:
                    continue
                comment_obj = comments_table(
                    comment_type=comment_data.comment_type,
                    comment_id=comment_data.comment_id,
                    pr_number=pr_data.number,
                    comment_body=comment_data.comment_body or "",
                    diff_hunk=comment_data.diff_hunk or "",
                    file_path=comment_data.file_path or "",
                    author=comment_data.author or "",
                    review_state=comment_data.review_state,
                )
                db.merge(comment_obj)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _migrate_comment_table_if_needed() -> None:
    """Recreate comment_table when the old single-PK schema is present."""
    insp = inspect(engine)
    if "comment_table" not in insp.get_table_names():
        return

    columns = {col["name"] for col in insp.get_columns("comment_table")}
    pk_cols = set(insp.get_pk_constraint("comment_table").get("constrained_columns") or [])

    needs_rebuild = (
        "comment_type" not in columns
        or "review_state" not in columns
        or pk_cols != {"comment_type", "comment_id"}
    )
    if not needs_rebuild:
        return

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS comment_table"))
    comments_table.__table__.create(bind=engine)


def init_db():
    """Physically creates the database file and all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)
    _migrate_comment_table_if_needed()


if __name__ == "__main__":
    init_db()
    print("Woohoo! Database tables created successfully!")
