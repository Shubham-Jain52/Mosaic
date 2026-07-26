"""Save scraped PR and comment data locally with SQLAlchemy."""

# pyrefly: ignore [missing-import]
from typing import List, Optional

from sqlalchemy import create_engine, ForeignKey, Text, String
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
    title: Mapped[str] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    comments: Mapped[List["comments_table"]] = relationship(
        "comments_table", back_populates="pr_relationship"
    )


class comments_table(Base):
    __tablename__ = "comment_table"
    comment_id: Mapped[int] = mapped_column(primary_key=True)
    pr_number: Mapped[int] = mapped_column(ForeignKey("pull_requests.number"), nullable=False)
    comment_body: Mapped[str] = mapped_column(Text)
    diff_hunk: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(String(255))
    author: Mapped[str] = mapped_column(String(50))

    pr_relationship = relationship("PULL_REQUEST", back_populates="comments")


def save_data_to_db(prs: List[PR_Structure]) -> None:
    """Persist a list of PRs and all of their review comments to SQLite."""
    db = session_local()
    try:
        for pr_data in prs:
            pr_obj = PULL_REQUEST(
                number=pr_data.number,
                title=pr_data.title,
                state=pr_data.state,
                description=pr_data.description,
            )
            db.merge(pr_obj)

            for comment_data in pr_data.comments:
                if comment_data.comment_id is None:
                    continue
                comment_obj = comments_table(
                    comment_id=comment_data.comment_id,
                    pr_number=pr_data.number,
                    comment_body=comment_data.comment_body or "",
                    diff_hunk=comment_data.diff_hunk or "",
                    file_path=comment_data.file_path or "",
                    author=comment_data.author or "",
                )
                db.merge(comment_obj)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Physically creates the database file and all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Woohoo! Database tables created successfully!")
