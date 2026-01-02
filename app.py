import os
import sys
import shutil
import fitz
from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session
from werkzeug.utils import secure_filename
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')
UPLOAD_FOLDER = 'uploads'
if os.path.exists(UPLOAD_FOLDER):
    shutil.rmtree(UPLOAD_FOLDER)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Use ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# OAuth
if os.getenv('FLASK_ENV') == 'development':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

oauth = OAuth(app)
github = oauth.register(
    name='github',
    client_id=os.getenv('GITHUB_CLIENT_ID'),
    client_secret=os.getenv('GITHUB_CLIENT_SECRET'),
    access_token_url='https://github.com/login/oauth/access_token',
    access_token_params=None,
    authorize_url='https://github.com/login/oauth/authorize',
    authorize_params=None,
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'},
)

ALLOWED_EXTENSIONS = {'epub', 'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Core Logic ---

def process_conversion(files, mode, options):
    """
    files: list of saved file paths
    mode: 'pdf', 'text', 'merge', 'protect'
    options: dict of extra params (password, etc.)
    returns: path to output file
    """
    output_filename = "converted_result"
    
    # 1. MERGE MODE (or generic PDF conversion of multiple files)
    if mode == 'merge' or (mode == 'pdf' and len(files) > 1):
        doc = fitz.open()
        for f in files:
            ext = f.rsplit('.', 1)[1].lower()
            if ext in ['png', 'jpg', 'jpeg']:
                img = fitz.open(f)
                rect = img[0].rect
                pdfbytes = img.convert_to_pdf()
                img.close()
                imgPDF = fitz.open("pdf", pdfbytes)
                page = doc.new_page(width=rect.width, height=rect.height)
                page.show_pdf_page(rect, imgPDF, 0)
            elif ext == 'pdf':
                src = fitz.open(f)
                doc.insert_pdf(src)
            elif ext == 'epub':
                src = fitz.open(f)
                pdf_bytes = src.convert_to_pdf()
                src_pdf = fitz.open("pdf", pdf_bytes)
                doc.insert_pdf(src_pdf)
        
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename + ".pdf")
        doc.save(output_path)
        return output_path

    # Single File Processing below
    filepath = files[0]
    ext = filepath.rsplit('.', 1)[1].lower()
    
    # 2. TO PDF
    if mode == 'pdf':
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename + ".pdf")
        if ext == 'epub':
            doc = fitz.open(filepath)
            pdf_bytes = doc.convert_to_pdf()
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)
        elif ext in ['png', 'jpg', 'jpeg']:
            # Single image to PDF
            img = fitz.open(filepath)
            pdfbytes = img.convert_to_pdf()
            with open(output_path, "wb") as f:
                f.write(pdfbytes)
        else:
            # Already PDF, just copy (unless protecting later?)
            shutil.copy(filepath, output_path)
            
        return output_path

    # 3. EXTRACT TEXT
    if mode == 'text':
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename + ".txt")
        doc = fitz.open(filepath) # Works for PDF and EPUB usually
        with open(output_path, "wb") as out:
            for page in doc:
                text = page.get_text().encode("utf8")
                out.write(text)
                out.write(b"\n\f")
        return output_path

    # 4. PROTECT
    if mode == 'protect':
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], "protected_" + output_filename + ".pdf")
        password = options.get('password', '')
        
        # Open source (assuming PDF for now, but could convert first)
        if ext != 'pdf':
            # Convert to PDF in memory first if needed, simplified here:
            pass 
        
        doc = fitz.open(filepath)
        # 256-bit AES encryption
        doc.save(output_path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
        return output_path
        
    return None


@app.route('/', methods=['GET'])
def index():
    user = session.get('user')
    return render_template('index.html', user=user)

@app.route('/convert', methods=['POST'])
def convert():
    user = session.get('user')
    if not user:
        flash('Please login to use the converter.')
        return redirect(url_for('index'))

    if 'files' not in request.files:
        flash('No files uploaded')
        return redirect(url_for('index'))

    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        flash('No files selected')
        return redirect(url_for('index'))

    # Save all files
    saved_paths = []
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            saved_paths.append(filepath)
            
    if not saved_paths:
        flash('No valid files found (epub, pdf, png, jpg)')
        return redirect(url_for('index'))

    mode = request.form.get('mode', 'pdf')
    password = request.form.get('password', '')
    
    try:
        output_file = process_conversion(saved_paths, mode, {'password': password})
        if output_file and os.path.exists(output_file):
            return send_file(output_file, as_attachment=True)
        else:
            flash("Conversion failed or mode not supported.")
            return redirect(url_for('index'))
    except Exception as e:
        flash(f"Error during conversion: {e}")
        return redirect(url_for('index'))

# Auth Routes
@app.route('/login')
def login():
    github = oauth.create_client('github')
    redirect_uri = url_for('authorize', _external=True)
    return github.authorize_redirect(redirect_uri)

@app.route('/callback')
def authorize():
    github = oauth.create_client('github')
    try:
        token = github.authorize_access_token()
        if token:
            resp = github.get('user')
            session['user'] = resp.json()
        return redirect('/')
    except Exception:
        flash("Login failed.")
        return redirect('/')
    
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
