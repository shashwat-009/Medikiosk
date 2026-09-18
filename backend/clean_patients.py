"""
Script to safely delete all test patients and their related records
(sessions, responses, summaries, documents, consents).
Doctors and system configuration are preserved.
"""
import os
import sys
from pathlib import Path

# Ensure backend directory is in sys.path and is current working directory
backend_dir = Path(__file__).resolve().parent
os.chdir(backend_dir)
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.db.database import SessionLocal
from app.models.summary import Summary
from app.models.response import Response
from app.models.consent import Consent
from app.models.document import Document
from app.models.session import Session
from app.models.patient import Patient


def clean_all_patients():
    db = SessionLocal()
    try:
        patient_count = db.query(Patient).count()
        session_count = db.query(Session).count()
        
        if patient_count == 0:
            print("Database me koi patient record nahi mila. Sab clean hai.")
            return

        print(f"Cleaning database: {patient_count} patients, {session_count} sessions found...")

        # Delete in order of foreign key dependencies
        deleted_summaries = db.query(Summary).delete()
        deleted_responses = db.query(Response).delete()
        deleted_consents = db.query(Consent).delete()
        deleted_documents = db.query(Document).delete()
        deleted_sessions = db.query(Session).delete()
        deleted_patients = db.query(Patient).delete()

        db.commit()

        print("Clean up successful!")
        print(f" - Patients deleted:  {deleted_patients}")
        print(f" - Sessions deleted:  {deleted_sessions}")
        print(f" - Responses deleted: {deleted_responses}")
        print(f" - Summaries deleted: {deleted_summaries}")
        print(f" - Consents deleted:  {deleted_consents}")
        print(f" - Documents deleted: {deleted_documents}")
        print("Note: Doctors aur unke accounts preserve rahe hain.")

    except Exception as exc:
        db.rollback()
        print(f"Error while cleaning patients: {exc}")
    finally:
        db.close()


if __name__ == "__main__":
    clean_all_patients()
