from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

# 1. Master Table: Librarians (Staff Accounts)
class Librarian(Base):
    __tablename__ = "librarians"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    password = Column(String(255), nullable=False)

# 2. Master Table: Categories (baru)
class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    nama = Column(String(60), unique=True, nullable=False)

# 3. Master Table: Books
class Book(Base):
    __tablename__ = "books"

    kode_buku = Column(String(20), primary_key=True, index=True)
    judul = Column(String(150), nullable=False)
    penulis = Column(String(100), nullable=False)
    stok = Column(Integer, nullable=False, default=1)
    # kolom baru (ditambahkan lewat app/migrate.py)
    penerbit = Column(String(100))
    isbn = Column(String(20))
    tahun = Column(Integer)
    sinopsis = Column(Text)
    category_id = Column(Integer, ForeignKey("categories.id"))
    cover_path = Column(String(255))
    dibuat = Column(String(20))

    category = relationship("Category")

# 4. Master Table: Members (Borrowers)
class Member(Base):
    __tablename__ = "members"

    id_member = Column(String(20), primary_key=True, index=True)
    nama = Column(String(100), nullable=False)
    no_hp = Column(String(20), nullable=False)
    # kolom baru
    email = Column(String(120))
    password = Column(String(255))
    status = Column(String(20), default="Aktif")
    bergabung = Column(String(20))

# 5. Transaction Table: Borrowings
class Borrowing(Base):
    __tablename__ = "borrowings"

    id = Column(Integer, primary_key=True, index=True)
    kode_buku = Column(String(20), ForeignKey("books.kode_buku"), nullable=False)
    id_member = Column(String(20), ForeignKey("members.id_member"), nullable=False)
    librarian_id = Column(Integer, ForeignKey("librarians.id"), nullable=True)
    tanggal_pinjam = Column(String(20), nullable=False)
    tanggal_kembali = Column(String(20), nullable=True)
    status = Column(String(20), default="Dipinjam")
    # kolom baru
    jatuh_tempo = Column(String(20))
    denda = Column(Integer, default=0)

    book = relationship("Book")
    member = relationship("Member")
    librarian = relationship("Librarian")

# Tabel baru
class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(40), primary_key=True)
    value = Column(String(100), nullable=False)

class Wishlist(Base):
    __tablename__ = "wishlist"

    id = Column(Integer, primary_key=True)
    id_member = Column(String(20), ForeignKey("members.id_member"), nullable=False)
    kode_buku = Column(String(20), ForeignKey("books.kode_buku"), nullable=False)

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    id_member = Column(String(20), ForeignKey("members.id_member"), nullable=False)
    pesan = Column(String(255), nullable=False)
    dibaca = Column(Integer, default=0)
    dibuat = Column(String(20), nullable=False)
