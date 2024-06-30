import sys
import dns.resolver
import re
import smtplib
import socket
import time
import csv
from PyQt5.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, 
                             QTableWidget, QTableWidgetItem, QFileDialog, QDialog, QLineEdit, 
                             QTextEdit, QHBoxLayout, QLabel, QHeaderView, QProgressBar)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# Function to check DNS status of a domain
def check_dns_status(domain):
    try:
        # Try to resolve the MX (Mail Exchange) record
        records = dns.resolver.resolve(domain, 'MX')
        mx_record = records[0].exchange.to_text()
        return mx_record
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.Timeout, dns.exception.DNSException):
        return None

# Function to validate an email
def validate_email(email):
    domain = email.split('@')[-1]
    mx_record = check_dns_status(domain)
    if not mx_record:
        return (False, "DNS check failed")

    # SMTP conversation
    try:
        smtp = smtplib.SMTP(timeout=10)
        smtp.connect(mx_record, 25)  # Specify port 25 explicitly
        smtp.helo(smtp.local_hostname)  # send HELO
        smtp.mail('test@email.com')   # use a valid sender email (no email will be sent)
        code, message = smtp.rcpt(email)  # RCPT TO
        smtp.quit()

        # SMTP response code 250 indicates the recipient address is valid
        return (code == 250, f"SMTP response code: {code}")
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, smtplib.SMTPHeloError, 
            smtplib.SMTPSenderRefused, smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError, 
            smtplib.SMTPException, socket.timeout) as e:
        return (False, str(e))
    except UnicodeError as e:
        return (False, f"Unicode error occurred: {e}")

# Function to check if an email address is valid
def is_valid_email(email):
    regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(regex, email) is not None

# Function to read emails from a file
def read_emails_from_file(file_path):
    emails = []
    try:
        with open(file_path, 'r') as file:
            if file_path.endswith('.csv'):
                reader = csv.reader(file)
                for row in reader:
                    emails.extend(row)
            else:
                emails = file.read().splitlines()
    except FileNotFoundError:
        pass
    return emails

# Function to save bad emails to a file
def save_bad_emails(bad_emails, output_file):
    with open(output_file, 'w') as file:
        for email in bad_emails:
            file.write(email + '\n')

class FilterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Filter Temp Mail Domains")
        self.setGeometry(100, 100, 400, 300)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        self.filter_text_edit = QTextEdit()
        self.filter_text_edit.setPlaceholderText("Enter temp mail domains, one per line")

        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_filters)

        layout.addWidget(self.filter_text_edit)
        layout.addWidget(save_button)

        self.setLayout(layout)

    def save_filters(self):
        filters = self.filter_text_edit.toPlainText().split('\n')
        self.parent().temp_mail_domains = set(filter(None, filters))
        self.accept()

class EmailVerifierApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CleanMail")
        self.setGeometry(100, 100, 1000, 600)
        self.init_ui()

        self.email_list = []
        self.temp_mail_domains = set()

    def init_ui(self):
        layout = QVBoxLayout()

        self.import_button = QPushButton("Import Emails")
        self.import_button.clicked.connect(self.import_emails)
        
        self.verify_button = QPushButton("Verify Emails")
        self.verify_button.clicked.connect(self.start_verification)

        self.filter_button = QPushButton("Filter Temp Mails")
        self.filter_button.clicked.connect(self.open_filter_dialog)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.import_button)
        button_layout.addWidget(self.verify_button)
        button_layout.addWidget(self.filter_button)

        self.email_table = QTableWidget(0, 3)
        self.email_table.setHorizontalHeaderLabels(["Email ID", "Status", "Log"])
        self.email_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        self.export_button = QPushButton("Export Results")
        self.export_button.clicked.connect(self.export_results)

        layout.addLayout(button_layout)
        layout.addWidget(self.email_table)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.export_button, alignment=Qt.AlignRight)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def import_emails(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Emails", "", "Text Files (*.txt);;CSV Files (*.csv)", options=options)
        if file_path:
            self.email_list = read_emails_from_file(file_path)
            self.update_email_table()

    def start_verification(self):
        self.verification_thread = EmailVerificationThread(self.email_list)
        self.verification_thread.progress.connect(self.update_progress)
        self.verification_thread.result.connect(self.update_table)
        self.verification_thread.start()

    def update_progress(self, progress):
        self.progress_bar.setValue(progress)

    def update_table(self, row, status, log):
        self.email_table.setItem(row, 1, QTableWidgetItem(status))
        self.email_table.setItem(row, 2, QTableWidgetItem(log))

    def open_filter_dialog(self):
        dialog = FilterDialog(self)
        dialog.exec_()
        self.filter_temp_mails()

    def filter_temp_mails(self):
        filtered_emails = [email for email in self.email_list if email.split('@')[-1] not in self.temp_mail_domains]
        self.email_list = filtered_emails
        self.update_email_table()

    def update_email_table(self):
        self.email_table.setRowCount(0)
        for email in self.email_list:
            row_position = self.email_table.rowCount()
            self.email_table.insertRow(row_position)
            self.email_table.setItem(row_position, 0, QTableWidgetItem(email))
            self.email_table.setItem(row_position, 1, QTableWidgetItem("Unverified"))
            self.email_table.setItem(row_position, 2, QTableWidgetItem(""))

    def export_results(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Results", "", "CSV Files (*.csv)", options=options)
        if file_path:
            with open(file_path, 'w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Email ID", "Status", "Log"])
                for row in range(self.email_table.rowCount()):
                    email = self.email_table.item(row, 0).text()
                    status = self.email_table.item(row, 1).text()
                    log = self.email_table.item(row, 2).text()
                    writer.writerow([email, status, log])

class EmailVerificationThread(QThread):
    progress = pyqtSignal(int)
    result = pyqtSignal(int, str, str)

    def __init__(self, email_list):
        super().__init__()
        self.email_list = email_list

    def run(self):
        total_emails = len(self.email_list)
        for i, email in enumerate(self.email_list):
            if is_valid_email(email):
                valid, log = validate_email(email)
                status = "Valid" if valid else "Invalid"
            else:
                status = "Invalid Format"
                log = "Invalid email format"
            self.result.emit(i, status, log)
            self.progress.emit((i + 1) * 100 // total_emails)
            time.sleep(1)  # Adding a 1-second delay between checks

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = EmailVerifierApp()
    window.show()
    sys.exit(app.exec_())
