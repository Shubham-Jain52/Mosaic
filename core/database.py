""" to save data locally, using SQL ALCHEMY"""

# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine, ForeignKey, Text, String
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, relationship
from .models import PR_Structure, Review_Comment_Structure

DB_URL = "sqlite:///mosaic.db"
engine = create_engine(DB_URL, echo=True)
session_local = sessionmaker(autocommit = False, autoflush = False, bind = engine)

class Base(DeclarativeBase):
    pass

class PULL_REQUEST(Base):
    __tablename__ = "pull_requests"
    number: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, nullable=True)
    comments:Mapped[list["comments_table"]] = relationship("comments_table",back_populates="pr_relationship")

class comments_table(Base):
    __tablename__ = "comment_table"
    comment_id : Mapped[int] = mapped_column(primary_key=True)
    pr_number:Mapped[int] = mapped_column(ForeignKey("pull_requests.number"), nullable=False)
    comment_body:Mapped[str] = mapped_column(Text)
    diff_hunk:Mapped[str] = mapped_column(Text)
    file_path:Mapped[str] = mapped_column(String(255))
    author:Mapped[str] = mapped_column(String(50))

    pr_relationship = relationship("PULL_REQUEST", back_populates="comments")

def save_data_to_db(pr: PR_Structure):
    db = session_local()
    for pr_data in pr:
        pr_obj = PULL_REQUEST(
            number=pr_data.number,
            title=pr_data.title,
            state=pr_data.state,
            description=pr_data.description,
            comments=pr_data.comments
        )
        db.add(pr_obj)
    db.commit()
    for comment_data in pr_data.comments:
        comment_obj = comments_table(
            comment_id=comment_data.comment_id,
            pr_number=comment_data.pr_number,
            comment_body=comment_data.comment_body,
            diff_hunk=comment_data.diff_hunk,
            file_path=comment_data.file_path,
            author=comment_data.author
        )
        db.add(comment_obj)
    db.commit()
    db.close()

def init_db():
    """Physically creates the database file and all tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("Woohoo! Database tables created successfully!")