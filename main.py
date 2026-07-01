import os, datetime, random, cloudinary, cloudinary.uploader, stripe
from flask import Flask, render_template, request,url_for, redirect, abort, session
from sqlalchemy import Integer, String, Date, DateTime, Boolean, Text, ForeignKey, Numeric
from flask_sqlalchemy import SQLAlchemy
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, IntegerField, FloatField, DecimalField, FileField, SelectMultipleField, SelectField
from flask_wtf import FlaskForm
from flask_login import UserMixin, login_user, login_required, current_user, logout_user, LoginManager
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.exc import IntegrityError
from dotenv import find_dotenv, load_dotenv
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange
from flask_mail import Mail, Message
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer import oauth_authorized
from functools import wraps
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView

# ვქმნით დეკლარაციის ბაზას რომელიც იქნება მოდელ კლასი როცა ჩვენს დატაბეიზს დავაინიცირებთ
class BaseClass(DeclarativeBase):
    pass

# ვტვირთავთ .env ფაილს და გუგლის ბლუპრინტს ვქმნით შემდგომში google ავტორიზაციის დასამაატებლად
load_dotenv(find_dotenv())
google_bp = make_google_blueprint(
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    scope=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ],
)

# ქლაუდინარი გვეხმარება ფოტოების ატვირთვაში და შემდეგ მათი url ის წამოღებაში რაც შემდეგ დატაბეიზში ინახება პროდუქტის ფოტოებისთვის
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# ადმინის წვდომის ინტეგრაცია რომელიც შემდეგ გამოიყენება add_items ის გვეედისთვის აქ .env იდან აღებულ ჩვენი ანუ ადმინის მეილი თუკი იქნება მოქმედი იუზერის მეილი მას ექნება წვდომა თუარა დაებლოკება წვდომა
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.email == os.getenv("ADMIN_MAIL"):
            return f(*args, **kwargs)
        else:
            return abort(403)
    return decorated_function

# აპლიკაციის ინციალიზაცია და ყველა საჭირო დატაბეიზის ან ვებსერვიისის დამატება ამ ჩვენი აპისთვის
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.register_blueprint(google_bp, url_prefix="/login")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
#ამ ხაზს ამოვშლი პროდუქშენისას და კიდე გუგლის ამ მისამართზე https://console.cloud.google.com/auth/clients/1091137987451-14eled9k1ch0q53g8n1v6rp4vjlvmpfn.apps.googleusercontent.com?project=hiphopstudio დავამატებ დომეინს ლოკალ ჰოსტის ნაცვლად
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

db = SQLAlchemy(model_class=BaseClass)
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER")
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER")
mail = Mail(app)
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# მონაცემები ნივთის ტიპებისთვის და თვეებისთვის
type_of_product = ['მობილური ტექნიკა', 'მობილურის აქსესუარები', 'კომპიუტერის ნაწილები', 'კომპიუტერის პერიფერიალები', 'მონიტორები']
months = {'01': "იან", '02': "თებ", '03': 'მარ', '04': 'აპრ', '05': 'მაი', '06': 'ივნ', '07': 'ივლ', '08': 'აგვ',
          '09': 'სექ', '10': 'ოქტ', '11': 'ნოე', '12': 'დეკ'}

sorted_by_names = {
    None : 'სტანდარტული',
    'price_asc' : 'ფასი: იაფიდან ძვირამდე',
    'price_desc' : 'ფასი: ძვირიდან იაფამდე',
    'stock_asc' : 'მარაგი: მცირედან მეტამდე',
    'stock_desc' : 'მარაგი: მეტიდან მცირამდე'
}


# ვერიფიკაციის კოდის გაგზავნის ლოგიკა რომელიც იყენებს flask_mail ს და ჩვენი ადმინის მეილით აგზავნის ვერიფიკაციის კოდს მომხმარებელთან რომელმაც ამ კოდით უნდა გაიარონ შემდეგ ვერიფიკაცია საიტზე წვდომისათვის
def send_Verification_code(user_mail, code):
    msg = Message(
        subject="ვერიფიკაციის კოდი",
        sender=app.config['MAIL_USERNAME'],
        recipients=[user_mail]
    )
    msg.body = f"ვერიფიკაციის კოდი : {code}\nვადა: 15 წუთი"
    mail.send(msg)


# დატაბეიზის თეიბლების შექმნა და მათი მონაცემების ტიპებისა და მათ შორის ურთიერთოებიბის გაწერა და შექმნა
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[String] = mapped_column(String, unique=True)
    username: Mapped[String] = mapped_column(String, unique=True)
    password: Mapped[String] = mapped_column(String, nullable=True)
    is_verified: Mapped[Boolean] = mapped_column(Boolean, default=False)
    verification_code: Mapped[String] = mapped_column(String, nullable=True)
    verified_code_expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_code_sent_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
    account_created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=lambda : datetime.datetime.now(datetime.timezone.utc))
    google_id: Mapped[String] = mapped_column(String, nullable=True)
    cart_items = relationship("cartItem", back_populates="user", cascade="all, delete-orphan")

class Item(db.Model):
    __tablename__ = 'items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[String] = mapped_column(String)
    description: Mapped[String] = mapped_column(String)
    price: Mapped[Numeric] = mapped_column(Numeric)
    stock: Mapped[Integer] = mapped_column(Integer)
    image_filename: Mapped[String] = mapped_column(String)
    type: Mapped[String] = mapped_column(String)
    cart = relationship("cartItem", back_populates="item")

class cartItem(db.Model):
    __tablename__ = 'cart_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quantity: Mapped[Integer] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'))
    item_id: Mapped[int] = mapped_column(Integer, ForeignKey('items.id'))
    user = relationship("User", back_populates="cart_items")
    item = relationship("Item", back_populates="cart")

# flask ის ფორმების შექმნა

class RegisterForm(FlaskForm):
    username = StringField('მომხმარებლის სახელი', validators=[DataRequired()])
    email = StringField('ელ-ფოსტა', validators=[DataRequired(), Email()])
    password = PasswordField('პაროლი', validators=[DataRequired(), Length(min=8, max=32)])
    password2 = PasswordField('გაიმეორე პაროლი', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField("ანგარიშის შექმნა")


class LoginForm(FlaskForm):
    email = StringField('ელ-ფოსტა', validators=[DataRequired()])
    password = PasswordField('პაროლი', validators=[DataRequired()])
    remember_me = BooleanField('დამიმახსოვრე')
    submit = SubmitField("შესვლა")

class AddItems(FlaskForm):
    name = StringField('პროდუქტის სახელი',  validators=[DataRequired(), Length(min=2, max=200)])
    description = TextAreaField('აღწერა', validators=[DataRequired(), Length(min=10)])
    price = DecimalField('ფასი (₾)',   validators=[DataRequired(), NumberRange(min=0.01)])
    stock = IntegerField('მარაგი', validators=[DataRequired(), NumberRange(min=0)])
    type = SelectField('აირჩიე პროდუქტის ტიპი', choices=type_of_product, validators=[DataRequired()])
    img = FileField('პროდუქტის ფოტო')
    submit = SubmitField('გამოქვეყნება')

# flask_admin ის გამოყენებით ადმინის გვერდზე წვდომის გაცემა არ გაცემის ლოგიკა
class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.email == os.getenv("ADMIN_MAIL")

    def inaccessible_callback(self, name, **kwargs):
        return abort(403)

# ამ ადმინის გვერდზე ვამატებთ ჩვენს დატაბეიზის ცხრილებს რომელიც ადმინს გამოუჩნდება
admin = Admin(app, index_view=MyAdminIndexView())
admin.add_view(ModelView(User, db))
admin.add_view(ModelView(Item, db))
admin.add_view(ModelView(cartItem, db))

# თავიდან ვქმნით დატაბეიზს თუკი ის არ არსებობს
try:
    with app.app_context():
        db.create_all()
except Exception as e:
    pass

# აითემების დასორტირების ლოგიკა
def sort_items(data, sort):
    if sort == 'price_asc':
        data = data.order_by(Item.price.asc())
    elif sort == 'price_desc':
        data = data.order_by(Item.price.desc())
    elif sort == 'stock_asc':
        data = data.order_by(Item.stock.asc())
    elif sort == 'stock_desc':
        data = data.order_by(Item.stock.desc())
    return data

# ვერიფიკაციის კოდის გაგზავნისას კოდის გენერაცია და მისი შენახვა დატაბეიზში ასევე მისი გაგზავნისა და მოქმედების ვადების შენახვაც
def store_code(user):
    user.verified_code_expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=15)
    user.verification_code = random.randint(1000, 9999)
    user.verified_code_sent_at = datetime.datetime.now(datetime.timezone.utc)
    db.session.commit()
    send_Verification_code(user.email, user.verification_code)

# იუზერის ჩატვირთვა აპლიკაციაში
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# მთავარი გვერდი აქ წვდომა აქვს ნებისმიერ იუზერს არის იგი რეგისტრირებული თუარა
@app.route("/")
def index():
    # ვიღებთ რექვესტის url იდან ყველა პარამეტრს კატეგორიის, მოქმედი გვერდის ინდექსის, სორტირების ხერხის შესახებ
    category=request.args.get('category')
    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort')
    page_count, max_per_page = 0, 9

    # თუკი იუზერი რეგისტრირებულია ჩვენ ვითვლით მათ კარტაში აითემების რაოდენობას თუარა ვწერთ 0 ს
    if current_user.is_authenticated: cart_items_count = cartItem.query.filter_by(user_id=current_user.id).count()
    else: cart_items_count = 0

    # მითითებული კატეგორიის არსებობის შემთხვევაში დატაბეიზიდან ვიღებთ მხოლოდ ამ კატეგორიის მქონე აითემებს
    if category: data =Item.query.filter_by(type=category)
    else: data = Item.query

    # სორტირების ლოგიკის მქონე ფუნქციას გადავცემთ ჩვენს მონაცემებს და ის ასორტირებს მათ ჩვენი სურვილისამებრ
    data = sort_items(data, sort).all()
    sorted_by = sorted_by_names[sort]

    # აქ ვითვლით მონაცემთა რაოდენობას და თითო გვერდზე ვსვავთ ჩვენი სასურველი რაოდენობის პროდუქტს და ასევე ვამატებთ ლინკებს შემდეგი მაგდენი აითმის სანახავად
    full_data_count=len(data)
    page_count = len(data) // max_per_page if len(data) % max_per_page == 0 else len(data) // max_per_page + 1
    data = data[(page - 1) * max_per_page: page * max_per_page]

    return render_template("index.html", products=data, category=category, page=page, page_count=page_count, full_data_count=full_data_count, sorted_by=sorted_by, sorted=sort, cart_items_count=cart_items_count)

# აითემების გვერდი სადაც გადავცემთ ჩვენ აითემის id ს რომლითაც ვიღებთ შემდეგში ჩვენ ამ აითემს და მის გვერდს გადავცემთ მის მონაცემებს დატაბეიზიდან და თუკი ეს მონაცემები ვერ ამოვიღეთ არასწორი აითემის აიდის გამო ვაბრუნებთ მომხმარებელს უკან მთავარ გვერდზე
@app.route('/item/<id>', methods=['GET', 'POST'])
def item(id):
    data = Item.query.filter_by(id=id).first()
    if not data : return redirect(url_for('index'))
    related_items = Item.query.filter_by(type=data.type).all()
    related_items = random.sample(related_items, 5)
    if current_user.is_authenticated: cart_items_count = cartItem.query.filter_by(user_id=current_user.id).count()
    else: cart_items_count = 0

    return render_template("item.html", product=data, related_items=related_items, cart_items_count=cart_items_count)

# დატაბეიზიდან ვიღებთ მოქმედი იუზერის კარტაში არსებულ აითემებს და ვარენდერებთ მათ კარტის გვერდზე აქ მოსახვედრად საჭიროა უკვე რეგისტრაცია
@app.route('/cart', methods=['GET', 'POST'])
@login_required
def cart():
    data = cartItem.query.filter_by(user_id=current_user.id).all()
    return render_template("cart.html", products=data)

# პროფილის გვერდი სადაც არის მომხმარებლის მონაცემები და მისი კარტის მონაცემები ასევე აქაც ნისახვედრად უნდა ვიყოთ რეგისტრირებული
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    cart_items = cartItem.query.filter_by(user_id=current_user.id).all()
    full_price = sum([item.item.price for item in cart_items])
    date_of_creation = current_user.account_created_at.strftime('%Y-%m-%d').split('-')
    created_at = f'{date_of_creation[2]} {months[date_of_creation[1]]} {date_of_creation[0]}წ.'
    return render_template("profile.html", cart_items=cart_items, full_price=full_price, created_at=created_at)

# კარტაში აითემის დამატების ლოგიკა აქ საჭიროა აითემის აიდი და იუზერის რეგისტრაცია
@app.route('/cart/add/<int:id>', methods=['GET', 'POST'])
@login_required
def add_cart(id):
    item = Item.query.filter_by(id=id).first()
    # ვეძებთ თუკი მომხმარებლის კარტაში არის უკვე მსგავსი აითემი და შემდგომში თუკი არის ახალი აითემის დამატების მაგივრად მის რაოდენობას ვუმატებთ აითემის რაოდენობას თუარა ვამატებთ ახალს
    cart_item = cartItem.query.filter_by(user_id=current_user.id, item_id=id).first()
    try:
        if cart_item and (cart_item.quantity + int(request.form.get('quantity'))) <= cart_item.item.stock: cart_item.quantity += int(request.form.get('quantity'))
        elif not cart_item : new_cart_item = cartItem(quantity=request.form.get('quantity'), user=current_user, item=item); db.session.add(new_cart_item)
        db.session.commit()
    except Exception as e:
        print(e)
    return redirect(url_for('cart'))

# კარტის დააბდეითება ამის გამოძახება ხდება კარტის გვერდიდან ჯავასკრიპტის მეშვეობის AJAX ით რომელიც fetch ის გამოყენებით აგზავნის მოთხოვნას ამ მისამართზე და ისე ვცვლით აითემების რაოდენობას და ვააბდეითებთ კარტას
@app.route('/cart/update', methods=['GET', 'POST'])
@login_required
def update_cart():
    # ვიღებთ ამათ AJAX მოთხოვნიდან JSON ის სახით
    item_id = request.json.get('item_id')
    action = request.json.get('action')

    # ვიღებთ კარტიდან აითემს რომელსაც ექნება მოქმედი იზუერის აიდი და JSON იდან აღებული აითემის აიდი
    cart_item = cartItem.query.filter_by(user_id = current_user.id, item_id=item_id).first()

    # თუკი ესეთი აითემი ვერ მოიძებნა ვაბრუნებთ ამას
    if not cart_item:
        return {"success": False}, 404

    # თუკი მოიძებნა აითემი და JSON იდან აღებული მოქმედება არის გაზრდა ვზრდით რაოდენობას თუკი ჩვენი აითემის სრულ რაოდენობას არ აღემატება
    if action == 'increase':
        if cart_item.quantity + 1 > cart_item.item.stock:
            return {"success": False}, 404
        cart_item.quantity += 1
    # აქ კი ვაკლებთ რაოდენობას ხოლო თუკი 0 ზე ჩამოვა რაოდენობა ვშლით მომხმარებლის კარტიდან ამ აითემს
    elif action == 'decrease':
        if cart_item.quantity > 1:
            cart_item.quantity -= 1
        else:
            db.session.delete(cart_item)
            db.session.commit()
            return {"success": True, "deleted": True}
    db.session.commit()
    return {"success": True, "quantity": cart_item.quantity, "stock": cart_item.item.stock}

# ამ როუტზე ისევ ვაგზავნით AJAX ით FETCH ის გამოყენებით მოთხოვნას გადმოსვლისას ჩვენ ვშლით აითემის აიდით და მოხმარებლის აიდის გამოყენებით სასურველ აითემს მომხმარებლის კარტიდან
@app.route('/cart/delete', methods=['GET', 'POST'])
@login_required
def delete_cart():
    item_id = request.json.get('item_id')
    user_id = current_user.id

    cart_item = cartItem.query.filter_by(user_id=user_id, item_id=item_id).first()

    if not cart_item:
        return {"success": False}, 404
    else:
        db.session.delete(cart_item)
        db.session.commit()
        return {"success": True, "deleted": True}

# ამ როუტზე მიმართვის შემდეგ მოქმედი მომხმარებლის კარტიდან ვშლით ყველა აითემს აქაც მიმართვას ვაკეთებთ FETCH ისა და AJAX გამოყენებით
@app.route('/cart/deleteAll', methods=['GET', 'POST'])
@login_required
def delete_all_cart():
    action = request.json.get('action')

    if action == "deleteAll":
        cartItem.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return {"success": True, "deleted": True}
    else:
        return {"success": False}, 403

# ჩექაუთის გვერდი რომელიც იქმნება STRIPE ის გამოყენებით ავტომატურად STRIPE API ს გამოყენებით
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    # ვიღებთ მომხმარებლის კარტიდან ყველა აითემს
    cart_items = cartItem.query.filter_by(user_id=current_user.id).all()

    #თუკი მომხმარებლის კარტაში არაფერია უკან ვაგზავნით მას კარტის გვერდზე
    if not cart_items:
        return redirect(url_for("cart"))

    # FOR ციკლის გამოყენებით line_items ში ვამატებთ STRIPE API ისთვის მისაღებ დატას რომელსაც ვადგენთ თითოეული აითემის გამოყენებით მომხმარებლის კარტიდან
    line_items = []
    for item in cart_items:
        line_items.append({
            'price_data': {
                'currency': 'gel', # ფასი რომ ლარში იყოს
                'product_data': {
                    'name': item.item.name,
                    'images': [item.item.image_filename],
                }, # ფოტოებისთვის და სახელისთვის ვამატებთ მონაცემებს დატაბეიზიდან
                'unit_amount': int(item.item.price) * 100, # აითემის ფასს ვამრავლებთ 100 რადგან STRIPE მუშაობს თეთრებში და გადაგვყავს ჩვენც თეთრებში
            },
            'quantity': item.quantity, # რაოდენობას ვამატებთ დატაბეიზიდან
        })

    # ვქმნით STRIPE ის სესიას ზემოტ შექმნილი მონაცემების მიხედვით და ეს თვითონვე დააგენერირებს ჩექაუთის გვერდს სრულად
    session_stripe = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=line_items,
        mode='payment',
        success_url=url_for('success', _external=True), # წარმატებით გადახდის შემდეგ გადაჰყავს /success გვერდზე
        cancel_url=url_for('cart', _external=True), # დაქენსელების შემთხვევაში გადაჰყავს უკან კარტის გვერდზე
        metadata={'user_id': current_user.id},
    )

    return redirect(session_stripe.url)

# წარმატების გადახდის გვერდი
@app.route('/success', methods=['GET', 'POST'])
@login_required
def success():
    return "success"

# ეს ვებჰუკი მუშაობს უკანა ფონზე და STRIPE ით გადახდისას წარმატებით გადახდის შემთხვევაში ნაყიდი აითემების რაოდენობას მოაკლებს აითემების სრულ რაოდენობას დატაბეიზში
@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            os.getenv("STRIPE_WEBHOOK_SECRET")
        )
    except Exception:
        return '', 400

    if event['type'] == 'checkout.session.completed':
        # იღებს იუზერის აიდის რომელმაც გადაიხადა და მისი კარტიდან შლის ამ აითემებს ასევე შლის სრული რაოდენობიდან ნაყიდი აითემების რაოდენობას
        user_id = event['data']['object']['metadata']['user_id']

        if not user_id: return 'Missing user id', 400

        for ci in cartItem.query.filter_by(user_id=user_id).all():
            if ci.item.stock >= ci.quantity:
                ci.item.stock = ci.item.stock - ci.quantity
        cartItem.query.filter_by(user_id=user_id).delete()
        db.session.commit()
    return '', 200

# სერჩის როუტი რომლიც მუშაობს მთავარი გვერდიდან POST მეთოდით გამოგზავნილი მოთხოვნით სერჩის ფორმიდან
@app.route('/search', methods=['GET', 'POST'])
def search():
    # იღებს საძიებო სიტყვას სორტირების მეთოდს და მქომედი გვერდის ინდექსს
    keyword = request.args.get('keyword')
    sort = request.args.get('sort')
    page = request.args.get('page', 1, type=int)
    page_count, max_per_page = 0, 9

    # თუკი საძიებო სიტყვა ვერ ამოვიღეთ ვაგზავნით მომხმარებელს ისევ მთავარ გვერდზე
    if not keyword: return redirect(url_for("index"))
    else:
        # ვიღებთ ყველა იმ აითემს რომლის სახელიც შეესაბამება საძიებო სიტყვას
        data = Item.query.filter(Item.name.ilike('%' + keyword + '%'))
        # ვასორტირებთ სორტირების მეთოდის მიხედვით
        data = sort_items(data, sort).all()
        sorted_by = sorted_by_names[sort]

        # როგორც მთავარ გვერდზე აქაც იგივენაირად ვაკეთებთ ყველაფერს ვითვლით სრულ რაოდენობას ვყოფთ ერთ გვერდზე წარმოდგენილი აითემების ჩვენი სასურველ რაოდენობაზე და მაგის მიხედვით ვაწყობთ ბათონებს შემდეგი გვერდებისთვის
        full_data_count = len(data)
        page_count = len(data) // max_per_page if len(data) % max_per_page == 0 else len(data) // max_per_page + 1
        data = data[(page - 1) * max_per_page: page * max_per_page]

        return render_template("index.html", products=data, keyword=keyword, sorted=sort, sorted_by=sorted_by, full_data_count=full_data_count, page_count=page_count, page=page)


# ახალი აითემების დამატების გვერდი რომელზეც წვდომა აქვს მხოლოდ ადმინის მეილით დარეგისტრირებულ იუზერს და ამით ვამატებთ ახალ აითემებს ჩვენს დატაბეიზში
@app.route("/add_items", methods=["GET", "POST"])
@login_required
@admin_required
def add_item():
    # ვქმნით ფორმას flask_form ის გამოყენებით უკვე ზემოთ დეკლარირებული AddItems ფორმის გამოყენებით და შემდეგ ჩვეულებრივ თუკი გაივლის ყველა ჩვენს მიერ დაკისრებულ მოთხოვნას იქმნება ამ ფორმიდან აღებული მონაცემებით ახალი აითემი და ემატება დატაბეიზში
    form = AddItems()
    if form.validate_on_submit():
        image_file = form.img.data
        result = cloudinary.uploader.upload(image_file)
        image_url = result["secure_url"]

        new_item = Item(
            name=form.name.data,
            description=form.description.data,
            price=float(form.price.data),
            stock=int(form.stock.data),
            image_filename=image_url,
            type=form.type.data,
        )
        try:
            db.session.add(new_item)
            db.session.commit()
        except Exception as e:
            print(e)
        else:
            return redirect(url_for("index"))

    return render_template("add_items.html", form=form)

# login ის გვერდი სადაც არის ისევ flask_form ა და იუზერი გადის რეგისტრაციას სრულიად ჩვეულებრივ
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for("index"))
    form = LoginForm()
    error = request.args.get("error")
    if form.validate_on_submit():
        # ვეძებთ იუზერს ფორმაში შეყვანილი მეილის მიხედვით და თუკი ვიპოვით შემდეგ გადის ყველა დანარჩენ შემოწმებას თუკი ვერ მოიძებნა ვაგზავნით შესაბამის შეტყობინებას
        user = User.query.filter_by(email=form.email.data).first()

        if user:
            # მოწმდება თუკი იუზერი არის დარეგისტრირებული მხოლოდ გუგლის რეგისტრაციის გამოყენებით და თუკი ეს ასეა ჩვეულებრივი რეგისტრაციის საშუალებას არ აძლევს მას და ვაგზავნით შესაბამის შეტყობინებას
            if user.google_id and not user.password:
                error = "ეს ანგარიში Google-ით არის რეგისტრირებული. გამოიყენე Google-ით შესვლა."
                return render_template("login.html", form=form, error=error)
            # ვამოწმებთ პაროლი თუ სწორია შემდეგ ვამოწმებთ თუკი იუზერს აქვს გავლილი ვერიფიკაცია მეილის 4 ნიშნა კოდის გამოყენებით და თუკი აქვს შედის აპლიკაციაში თუარა გადადის ვერიფიკაციის გვერდზე ყველა შემთხვევაში ჩვენ ვაგზავნით შესაბამის შეტყობინებას
            if check_password_hash(user.password, form.password.data):
                if user.is_verified:
                    login_user(user)
                    return redirect(url_for("index"))
                else:
                    return redirect(url_for('sendCode', id=user.id))
            else:
                error = "არასწორი პაროლი"
        else:
            error = "მსგავსი მონაცემებით მომხმარებელი არ არსებობს"
    return render_template("login.html", form=form, error=error)

# რეგისტრაციის გვერდი სადაც ისევე flask_form ით ვაკეთებთ ყველაფერს ვარეგისტრირებთ იუზერს ჩვენს აპლიკაციაში, ვინახავთ მის მონაცემებს დატაბეიზში თუკი ეს მომხმარებელი უკვე ამ მეილთ ან სახელით არაა რეგისტრირებული და შემდეგ გადაგვყავს ის ვერიფიკაციის გვერდზე
@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    error = None

    if request.method == "POST":
        if form.validate_on_submit():
            new_user = User(username=form.username.data, email=form.email.data, password=generate_password_hash(password=form.password.data, method='pbkdf2:sha256', salt_length=8))
            try:
                db.session.add(new_user)
                db.session.commit()
            except IntegrityError:
                error = "მომხმარებელი მსგავსი მონაცემებით უკვე არსებობს"
            except Exception as e:
                print(e)
            else:
                return redirect(url_for("sendCode", id=new_user.id))
        elif form.password.data != form.password2.data:
            error ="პაროლები არ ემთხვევა ერთმანეთს"
    return render_template("register.html", form=form, error=error)

# პაროლის შეცვლის გვერდი აქ ეს გვერდი იყოფა ორ როუტად ერთი პირველი არის ფორმა რომლშიც მომხმარებელმა უნდა ჩაწეროს მისი ემეილი რომელზეც ამ პაროლის შეცვლა უნდა და თუკი ესეთ იუზერს იპოვის გადაჰყავს ის მეორე ეტაპზე და /reset_password როუტზე, ხოლო თუკი მსგავსი მეილით არ არსებობს მომხმარებელი ჩვენ მათ ვუგზავნით შესაბამის შეტყობინებას
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    error = None
    if request.method == "POST":
        # თუკი ამ სესიაში არის უკვე ეს მეილი დამატებული მაშინ პირდაპირ გადაგვყავს მეორე ეტაპზე
        if session.get('reset_email'):
            return redirect(url_for("reset_password"))
        email = request.form.get("email")
        user = User.query.filter_by(email=email).first()
        if user:
            # ფლასკის სესიის გამოყენებით ამ სესაში ვინახავთ კოდის გაგზავნის მეილს
            session['reset_email'] = user.email
            store_code(user)
            return redirect(url_for("reset_password"))
        else: error = "მომხმარებელი მსგავსი ელ-ფოსტით არ არსებობს"

    return render_template("forgotPassword.html", error=error)

# პაროლის შეცვლის მეორე ეტაპის როუტი
@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    # ამ სესიიდან ვიღებთ ამ forgot_password იდან დამატებულ reset_email ს და მისის გამოყენებით ვიღებთ სასურველ იუზერს დატაბეიზიდან
    email = session.get("reset_email")
    user = User.query.filter_by(email=email).first()
    # რექვესტის url იდან ვიღებთ პარამეტრს send_again რომლის url ში არსებობის შემთხვევაში ვამოწმებთ ქვემოთ მოცემული if elif ის გამოყენებით თუკი ბოლო კოდის გაგზავნიდან არის გასული 30 წამზე მეტი და თუ ეს ასეა ვაგზავნით ახალ კოდს ხოლო თუკი არა ვაგზავნით შესაბამის შეტყობინებას
    # ეს send_again ი იქნება url ში მხოლოდ მაშინ როცა იუზერი დააჭერს თავიდან გაგზავნის ღილაკს
    send_again = request.args.get("send_again")
    error = None
    if send_again and (user.verified_code_sent_at and (user.verified_code_sent_at + datetime.timedelta(seconds=30)) < datetime.datetime.now(datetime.timezone.utc)) or not user.verified_code_sent_at: store_code(user)
    elif send_again and user.verified_code_sent_at and (user.verified_code_sent_at + datetime.timedelta(seconds=30)) > datetime.datetime.now(datetime.timezone.utc): error = "დაიცადეთ 30 წამი ახალის კოდის გასაგზავნად"

    if request.method == "POST":
        # ვიღებთ კოდს და პაროლებს html ფორმიდან და ვამოწმებთ პირველ რიგში თუკი პაროლები ემთხვევა ერთმანეთს თუკი ასე არაა ვაგზავნით შესაბამის შეტყობინებას
        # თუკი პაროლები ერთმანეთის ტოლია შემდეგ ვამოწმებთ თუკი შეყვანილი კოდი ტოლია მომხმარებლის კოდის დატაბეიზში და მისი მოქმედების ვადას თუკი ის ისევ აქტიურია თუ ეს ასე არაა მაშინ ორივე შემთხვევაში ვაგზავნით შესაბამის შეტყობინებას
        # თუკი ყველაფერი რიგზეა მაშინ ჩვენ ვცვლით პაროლს და ვინახავთ ახალ პაროლს დატაბეიზში
        code = ''.join(request.form.get(f'num{i+1}', '') for i in range(4))
        password = request.form.get('password')
        repeat_password = request.form.get('confirm_password')
        if password != repeat_password:
            error = "პაროლები არ ემთხვევა"
        else:
            if user.verification_code == code:
                if user.verified_code_expires_at > datetime.datetime.now(datetime.timezone.utc):
                        try:
                            user.password = generate_password_hash(password=password, method='pbkdf2:sha256', salt_length=8)
                            db.session.commit()
                            session.pop('reset_email', None)
                        except Exception as e:
                            print(e)
                        else:
                            return redirect(url_for("login"))
                else:
                    error = "ვერიფიკაციის კოდს ვადა გაუვიდა"
            else:
                error = "ვერიფიკაციის კოდი არასწორია"

    return render_template("forgotPassword.html", validated=True, error=error)

# კოდის გაგზავნის როუტი რომელიც გამოიყენება აქაუნთის ვერიფიკაციისთვის რეგისტრაციის შემდეგ აქ მოთხოვნა გადაიცემა ისევ ajax ისა და fetch ის გამოყენებით  /verify გვერდიდან და ასევე რეგისტრაციიდან აქ გადმოსამისამართებით
@app.route("/send_code", methods=["GET", "POST"])
def sendCode():
    # რექვესტსი url იდან იღებს არგუმენტს რომელიც არის id ამ შემთხვევაში
    # ამ id ს ვერ ამოღების შემთხვევაში ვაბრუნბთ მომხმარებელს მთავარ გვერდზე
    id = request.args.get('id')
    error = None
    if not id : return redirect(url_for("index"))
    else:
        # ვიღებთ იუზერს ამ id ს გამოყენებით
        # თუკი ვერ ამოვიღებთ იუზერს მათ ვაბრუნებთ რეგისტრაციის გვერდზე
        # თუ ამოვიღებთ მაგრამ ის უკვე ვერიფიცირებულია მაშინ ჩვეულებრივ შეგვყავს ის მთავარ გვერდზე
        # ხოლო თუ ზემოთ ჩამოთვლილი არ მოხდა ჩვენ ვაგზავნით კოდს
        user = User.query.filter_by(id=id).first()
        if not user : return redirect(url_for("login"))
        if user.is_verified : return redirect(url_for("index"))
        else:
            # ვამოწმებთ თუკი ბოლო გაგზავნის შემდეგ გასულია 30 წამზე მეტი თუკი ასეა ვაგზავნით კოდს თუარა ვაგზავნით შესაბამის შეტყოვინებას ოღონდ ამ შემთხვევაში ვაგზავნით მას json ფორმატით javascript ში სადაც მერე ვამუშავებ მას და გადავცემ error ის მესიჯის ქარდს
            if (user.verified_code_sent_at and (
                    user.verified_code_sent_at + datetime.timedelta(seconds=30)) < datetime.datetime.now(
                datetime.timezone.utc)) or not user.verified_code_sent_at:
                store_code(user)
                return {"Success": True}, 200
            elif user.verified_code_sent_at and (
                    user.verified_code_sent_at + datetime.timedelta(seconds=30)) > datetime.datetime.now(
                datetime.timezone.utc):
                error = "დაიცადეთ 30 წამი ახალის კოდის გასაგზავნად"
                return {"Success": False, "error": error}, 403

        return redirect(url_for("verify", id=id, error=error))

# ვერიფიკაციის გვერდი
@app.route("/verify", methods=["GET", "POST"])
def verify():
    # ვიღებთ აიდის url დან ისევ
    id = request.args.get('id')
    # ამ აიდის არ არსებობის გვერდზე ვაბრუნებთ მათ მთავარ გვერდზე
    if not id:
        return redirect(url_for("index"))
    else:
        # კოდს ვიღებთ ფორმიდან
        code = ''.join(request.form.get(f'otp{i}', '') for i in range(4))
        # ვიღებთ იუზერს დატაბეიზიდან იმ აიდით რომელიც წეხან url დან ამოვიღეთ
        user = User.query.filter_by(id=id).first()
        # თუ იუზერი ვერ მოიძებნა ვაბრუნებთ მათ რეგისრაციის გვერდზე
        if not user : return redirect(url_for("login"))
        # ვიღებთ error ის მესიჯს url დან თუკი ის არ არსებობს მას ვაძლევთ None მნიშვნელობას ეს ერორი არსებობის შემთხვევაში გადმოცემულია send_code იდან
        error = request.args.get("error", None)
        # თუკი იუზერი უკვე ვერიფიცირებულია გადაგვყავს ის მთავარ გვერდზე
        if user.is_verified : return redirect(url_for("index"))

        if request.method == "POST":
            # ვამოწმებთ თკი ვერიფიკაციის კოდი და მისი მოქმედების ვადა ვალიდურია და თუკი ეს ასეა მაშინ მას ვარეგისტრირებთ და გადაგვყავს მთავარ გვერდზე
            # თუკი არასწორია კოდი ან დრო გასულია ვაბრუნებთ შესაბამის შეტყობინებას
            if user.verification_code == code and user.verified_code_expires_at > datetime.datetime.now(datetime.timezone.utc):
                user.is_verified = True
                db.session.commit()
                login_user(user)
                return redirect(url_for("index"))
            elif user.verified_code_expires_at < datetime.datetime.now(datetime.timezone.utc):
                error = "მომქმედების ვადა ამოიწურა სცადეთ ახალი კოდის გაგზავნა"
            else:
                error = "არასწორი კოდი"
        return render_template("verify.html", user=user, error=error)

# გუგლით ავტორიზაციის როუტი
@oauth_authorized.connect_via(google_bp)
def google_authorized(blueprint, token):
    # token ს და ბლუპრინტს ვიღებთ google დან თუკი ეს ტოკენი ვერ ამოვიღეთ მაშინ გადაგვყავს უკან login გვერდზე და შესაბამის შეტყობინებას ვაგზავნით
    if not token:
        return redirect(url_for("login", error='Google-ით შესვლა გაუქმდა'))

    res = blueprint.session.get("/oauth2/v2/userinfo")

    # თუკი ინფორმაცია ვერ ამოიღო google მა მაშინ გადაგვყავს ისევ login გვერდზე იუზერი და შესაბამის შეტყობინებას ვაგზავნით
    if not res.ok:
        return redirect(url_for("login", error="Google-იდან ინფორმაციის მიღება ვერ მოხერხდა"))

    # ვიღებთ შესაბამის ინფორმაციას გუგლიდან ამ რეგისტრირებული აქაუნთის შესახებ

    google_data = res.json()

    google_id = google_data["id"]
    email = google_data["email"]
    name = google_data["name"]

    # ვამოწმებთ თუკი ამ google_id არის იუზერი უკვე ბაზაში თუ ეს ასეა მაშინ ჩვენ შეგვყავს იუზერი აპლიკაციაში და გადგვყავს ის მთავარ გვერდზე
    user = User.query.filter_by(google_id=google_id).first()
    if user:
        login_user(user)
        return redirect(url_for("index"))

    # თუ იუზერი მსგავსი გუგლი აიდით არაა მაშინ ვამოწმებთ თუ მსგავსი მეილითაა და თუ ეს ასეა მაშინ ამ მომხმარებელის მონაცამებს ვამტებთ google_id ს და შეგვყავს ისე აპლიკაციაში და გადაგვყავს მთავარ გვერდზე
    user = User.query.filter_by(email=email).first()
    if user:
        user.google_id = google_id
        db.session.commit()
        login_user(user)
        return redirect(url_for("index"))

    # გოგლის ინფორმაციიდან აღებული იუზერნეიმი გადაგვყავს დაბალ რეგისტრში
    username = name.lower()
    # ვამოწმებთ თუკი მსგავსი იუზერნეიმით ვინმე არის უკვე რეგისტრირებული და თუკი ეს ასეა მაშინ while ის დახმარებით ყოველჯერზე გადააკეთებს მას ბოლოში 3 დან 5 მდე ციფრიანი რიცხვის დამატებით
    while User.query.filter_by(username=username).first():
        username = username + str(random.randint(100, 10000))

    # ვქმნით გუგლის მონაცემებით ახალ იუზერს და ვამატებთ მას დატაბეიზში შემდეგ მას ვარეგისტრირებთ აპლიაკციაში და გადაგვყავს მთავარ გვერდზე
    # ამ ხერხით დარეგისტრირებული მომხმარებლებს არ აქვთ პაროლი თუ შემდეგ არ დაამატეს და ვერიფიკაცია ავტომატურად აქვთ გავლილი
    new_user = User(
        username = username,
        email = email,
        google_id = google_id,
        is_verified = True,
        password = None
    )
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return redirect(url_for("index"))

# ლოგაუთის როუტი რომელსაც უბრალოდ გამოჰყავს იუზერი აპლიკაციიდან და გადაჰყავს ის login ის ფეიჯზე
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# აქაუნთის წაშლის როუტი
@app.route("/delete_account", methods=["GET", "POST"])
@login_required
def delete_account():
    # ვიღებთ ისევ ერორის მესიჯს url დან არსებობის შემთხვევაში
    error = request.args.get("error", None)
    if request.method == "POST":
        # კოდს ვიღებთ ფორმიდან და ვამოწმებთ თუკი ის შეესაბამება მოქმედი იუზერის ვერიფიკაციის კოდს დატაბეიზიდან და ამ კოდის მოქმედების ვადა თუკი ისევ ვალიდურია
        # თუ ეს ასეა მაშინ ვშლით იუზერს დატაბეიზიდან და გადაგვყავს ის login გვერდზე
        # თუ ეს ასე არაა მაშინ ვაბრუნებთ შესაბამის შეტყობინებას
        code = ''.join([request.form.get(f'num{i+1}', '') for i in range(4)])
        if code == current_user.verification_code and current_user.verified_code_expires_at > datetime.datetime.now(datetime.timezone.utc):
            db.session.delete(current_user)
            db.session.commit()
            return redirect(url_for("login"))
        elif code != current_user.verification_code:
            error = 'კოდი არასწორია'
        else:
            error = 'კოდის მოქმედების ვადა ამოწურულია, სცადეთ ახალი კოდის გაგზავნა'
    return render_template("delete_confimation.html", error=error)

# აქაუნთის წაშლის კოდის გაგზავნა ამაზე მოთხოვნა იგზავნება შესაბამისი ფორმის და post method ის გამოყენებით
@app.route("/delete_account/send_code", methods=["POST"])
@login_required
def send_code():
    # წამოწმებთ თუკი 30 წამი არის გასული ბოლო კოდის გაგზავნიდან თუ ეს ასეა მაშინ ვაგზავნით კოდს, წინააღმდეგ შემთხვევაში ვაგზავნით შესაბამის შეტყობინებას
    if current_user.verified_code_sent_at and current_user.verified_code_sent_at + datetime.timedelta(seconds=30) > datetime.datetime.now(datetime.timezone.utc):
        return redirect(url_for("delete_account", error="დაელოდედ 30 წამის გასვლას"))
    store_code(current_user)
    return redirect(url_for("delete_account"))

if __name__ == "__main__":
    app.run(debug=True)