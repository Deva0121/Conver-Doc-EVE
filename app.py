import os
import sys
from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session
import fitz
from werkzeug.utils import secure_filename
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Use ProxyFix for correct URL generation behind Render's proxy
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Allow HTTP for OAuth ONLY in development
if os.getenv('FLASK_ENV') == 'development':
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# OAuth setup
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

# --- Conversion Functions ---

def convert_epub_to_pdf(input_path, output_path):
    doc = fitz.open(input_path)
    pdf_bytes = doc.convert_to_pdf()
    pdf_doc = fitz.open("pdf", pdf_bytes)
    pdf_doc.save(output_path)

def convert_pdf_to_text(input_path, output_path):
    doc = fitz.open(input_path)
    with open(output_path, "wb") as out:
        for page in doc:
            text = page.get_text().encode("utf8")
            out.write(text)
            out.write(b"\n\f")

def convert_images_to_pdf(image_paths, output_path):
    doc = fitz.open()
    for img_path in image_paths:
        img = fitz.open(img_path)
        rect = img[0].rect
        pdfbytes = img.convert_to_pdf()
        img.close()
        imgPDF = fitz.open("pdf", pdfbytes)
        page = doc.new_page(width = rect.width, height = rect.height)
        page.show_pdf_page(rect, imgPDF, 0)
    doc.save(output_path)

# --- Routes ---

@app.route('/')
def dashboard():
    user = session.get('user')
    return render_template('dashboard.html', user=user)

@app.route('/tool/epub-to-pdf', methods=['GET', 'POST'])
def epub_to_pdf():
    user = session.get('user')
    if request.method == 'POST':
        if not user:
            flash('Please login to convert files.')
            return redirect(request.url)
        
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        
        if file.filename == '' or not allowed_file(file.filename):
            flash('Invalid or no file selected.')
            return redirect(request.url)

        if not file.filename.lower().endswith('.epub'):
             flash('Please upload an EPUB file.')
             return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        pdf_filename = filename.rsplit('.', 1)[0] + '.pdf'
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
        
        try:
            convert_epub_to_pdf(filepath, pdf_path)
            return send_file(pdf_path, as_attachment=True)
        except Exception as e:
            flash(f'Error: {str(e)}')
            return redirect(request.url)
            
    return render_template('epub_to_pdf.html', user=user)

@app.route('/tool/pdf-to-text', methods=['GET', 'POST'])
def pdf_to_text():
    user = session.get('user')
    if request.method == 'POST':
        if not user:
            flash('Please login to convert files.')
            return redirect(request.url)
            
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        
        if file.filename == '' or not allowed_file(file.filename):
             flash('Invalid or no file selected.')
             return redirect(request.url)
             
        if not file.filename.lower().endswith('.pdf'):
             flash('Please upload a PDF file.')
             return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        txt_filename = filename.rsplit('.', 1)[0] + '.txt'
        txt_path = os.path.join(app.config['UPLOAD_FOLDER'], txt_filename)
        
        try:
            convert_pdf_to_text(filepath, txt_path)
            return send_file(txt_path, as_attachment=True)
        except Exception as e:
            flash(f'Error: {str(e)}')
            return redirect(request.url)

    return render_template('pdf_to_text.html', user=user)

@app.route('/tool/images-to-pdf', methods=['GET', 'POST'])
def images_to_pdf():
    user = session.get('user')
    if request.method == 'POST':
        if not user:
            flash('Please login to convert files.')
            return redirect(request.url)
            
        if 'files' not in request.files:
            flash('No files part')
            return redirect(request.url)
            
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            flash('No selected files')
            return redirect(request.url)
            
        image_paths = []
        for file in files:
             if file and allowed_file(file.filename):
                 filename = secure_filename(file.filename)
                 filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                 file.save(filepath)
                 image_paths.append(filepath)
        
        if not image_paths:
            flash('No valid images uploaded.')
            return redirect(request.url)

        pdf_filename = 'images_merged.pdf'
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
        
        try:
            convert_images_to_pdf(image_paths, pdf_path)
            return send_file(pdf_path, as_attachment=True)
        except Exception as e:
             flash(f'Error: {str(e)}')
             return redirect(request.url)

    return render_template('images_to_pdf.html', user=user)

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
    except Exception as e:
        flash(f"Login failed: {e}")
        return redirect('/')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
