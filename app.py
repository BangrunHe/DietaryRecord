from flask import Flask, render_template, request, jsonify,redirect,url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime,date,time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64
import os
import matplotlib

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False


app = Flask(__name__)
app.config['SECRET_KEY'] = '85858585afafafaf'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///diet.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ========== 数据模型 ==========
class UserConfig(db.Model):
    """用户配置表"""
    id = db.Column(db.Integer, primary_key=True)
    weight = db.Column(db.Float, nullable=False, default=60.0)  # 体重(kg)
    carb_per_kg = db.Column(db.Float, nullable=False, default=3.0)  # 碳水g/kg
    protein_per_kg = db.Column(db.Float, nullable=False, default=1.5)  # 蛋白质g/kg
    fat_per_kg = db.Column(db.Float, nullable=False, default=0.8)  # 脂肪g/kg
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class FoodTemplate(db.Model):
    """食物模板表"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # 食物名称
    carb_ratio = db.Column(db.Float, nullable=False)  # 碳水比例(百分比)
    protein_ratio = db.Column(db.Float, nullable=False)  # 蛋白质比例(百分比)
    fat_ratio = db.Column(db.Float, nullable=False)  # 脂肪比例(百分比)
    calories = db.Column(db.Float)  # 可选：每克热量
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DailyRecord(db.Model):
    """每日饮食记录表"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.utcnow().date)
    time = db.Column(db.Time, nullable=False, default=lambda: datetime.utcnow().time)
    food_name = db.Column(db.String(100), nullable=False)  # 食物名称
    weight = db.Column(db.Float, nullable=False)  # 重量(g)
    carb_ratio = db.Column(db.Float, nullable=False)  # 碳水比例(百分比)
    protein_ratio = db.Column(db.Float, nullable=False)  # 蛋白质比例(百分比)
    fat_ratio = db.Column(db.Float, nullable=False)  # 脂肪比例(百分比)
    notes = db.Column(db.Text)  # 备注
    template_id = db.Column(db.Integer, db.ForeignKey('food_template.id'))  # 关联模板
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ========== 核心计算逻辑 ==========
class NutrientCalculator:
    """营养素计算器"""

    @staticmethod
    def calculate_daily_goals(user_config):
        """计算每日营养素目标"""
        return {
            'carb': user_config.weight * user_config.carb_per_kg,  # 碳水(g)
            'protein': user_config.weight * user_config.protein_per_kg,  # 蛋白质(g)
            'fat': user_config.weight * user_config.fat_per_kg  # 脂肪(g)
        }

    @staticmethod
    def calculate_nutrient_amount(record):
        """计算单条记录的营养素含量"""
        carb_g = record.weight * record.carb_ratio / 100
        protein_g = record.weight * record.protein_ratio / 100
        fat_g = record.weight * record.fat_ratio / 100
        calories = (carb_g * 4) + (protein_g * 4) + (fat_g * 9)  # 计算热量

        return {
            'carb': carb_g,
            'protein': protein_g,
            'fat': fat_g,
            'calories': calories
        }

    @staticmethod
    def get_daily_summary(target_date=None):
        """获取每日摄入汇总"""
        if target_date is None:
            target_date = date.today()

        # 获取当天的所有记录
        records = DailyRecord.query.filter_by(date=target_date).all()

        total = {'carb': 0, 'protein': 0, 'fat': 0, 'calories': 0}

        for record in records:
            nutrients = NutrientCalculator.calculate_nutrient_amount(record)
            for key in total:
                total[key] += nutrients[key]

        return total

    @staticmethod
    def get_progress(user_config, daily_summary):
        """计算进度条数据"""
        goals = NutrientCalculator.calculate_daily_goals(user_config)

        progress = {}
        for nutrient in ['carb', 'protein', 'fat']:
            consumed = daily_summary.get(nutrient, 0)
            goal = goals.get(nutrient, 1)  # 避免除零
            percentage = min((consumed / goal) * 100, 100) if goal > 0 else 0

            progress[nutrient] = {
                'consumed': round(consumed, 1),
                'goal': round(goal, 1),
                'percentage': round(percentage, 1),
                'remaining': max(round(goal - consumed, 1), 0),
                'is_over': consumed > goal
            }

        return progress


# ========== 初始化数据库 ==========
def init_database():
    """初始化数据库，创建表和默认数据"""
    with app.app_context():
        db.create_all()

        # 如果没有用户配置，创建默认配置
        if UserConfig.query.first() is None:
            default_config = UserConfig(
                weight=60.0,
                carb_per_kg=3.0,
                protein_per_kg=1.5,
                fat_per_kg=0.8
            )
            db.session.add(default_config)

            # 添加一些示例模板
            sample_templates = [
                FoodTemplate(name="白米饭", carb_ratio=75, protein_ratio=7, fat_ratio=1),
                FoodTemplate(name="鸡胸肉", carb_ratio=0, protein_ratio=23, fat_ratio=2),
                FoodTemplate(name="鸡蛋", carb_ratio=1, protein_ratio=13, fat_ratio=11),
                FoodTemplate(name="炒饭", carb_ratio=40, protein_ratio=20, fat_ratio=10),
            ]

            for template in sample_templates:
                db.session.add(template)

            db.session.commit()
            print("数据库初始化完成！")


# ========== 路由和视图函数 ==========
@app.route('/')
def index():
    """首页/仪表盘"""
    # 获取用户配置
    user_config = UserConfig.query.first()

    # 获取今日汇总
    today = date.today()
    daily_summary = NutrientCalculator.get_daily_summary(today)

    # 计算进度
    progress = NutrientCalculator.get_progress(user_config, daily_summary)

    # 获取今日记录
    today_records = DailyRecord.query.filter_by(date=today).order_by(DailyRecord.time).all()

    # 获取食物模板
    templates = FoodTemplate.query.order_by(FoodTemplate.name).all()

    # 生成图表
    chart_url = generate_progress_chart(progress)

    return render_template('dashboard.html',
                           user_config=user_config,
                           progress=progress,
                           records=today_records,
                           templates=templates,
                           today=today,
                           chart_url=chart_url)


@app.route('/config', methods=['GET', 'POST'])
def config():
    """用户配置"""
    user_config = UserConfig.query.first()

    if request.method == 'POST':
        try:
            user_config.weight = float(request.form['weight'])
            user_config.carb_per_kg = float(request.form['carb_per_kg'])
            user_config.protein_per_kg = float(request.form['protein_per_kg'])
            user_config.fat_per_kg = float(request.form['fat_per_kg'])
            user_config.updated_at = datetime.utcnow()

            db.session.commit()
            flash('配置已更新！', 'success')
            return redirect(url_for('index'))
        except ValueError:
            flash('请输入有效的数字！', 'error')

    return render_template('config.html', config=user_config)


@app.route('/add_record', methods=['GET', 'POST'])
def add_record():
    """添加饮食记录"""
    templates = FoodTemplate.query.order_by(FoodTemplate.name).all()

    if request.method == 'POST':
        try:
            # 获取表单数据
            food_name = request.form['food_name']
            weight = float(request.form['weight'])

            # 检查是否使用了模板
            template_id = request.form.get('template_id')
            if template_id and template_id != 'custom':
                template = FoodTemplate.query.get(int(template_id))
                carb_ratio = template.carb_ratio
                protein_ratio = template.protein_ratio
                fat_ratio = template.fat_ratio
            else:
                # 自定义输入
                carb_ratio = float(request.form['carb_ratio'])
                protein_ratio = float(request.form['protein_ratio'])
                fat_ratio = float(request.form['fat_ratio'])

            # 解析时间
            time_str = request.form.get('time', datetime.now().strftime('%H:%M'))
            record_time = datetime.strptime(time_str, '%H:%M').time()

            # 创建记录
            record = DailyRecord(
                date=date.today(),
                time=record_time,
                food_name=food_name,
                weight=weight,
                carb_ratio=carb_ratio,
                protein_ratio=protein_ratio,
                fat_ratio=fat_ratio,
                notes=request.form.get('notes', ''),
                template_id=template_id if template_id != 'custom' else None
            )

            db.session.add(record)
            db.session.commit()
            flash('记录添加成功！', 'success')
            return redirect(url_for('index'))
        except ValueError as e:
            flash(f'请输入有效的数字！错误: {str(e)}', 'error')
        except Exception as e:
            flash(f'添加失败: {str(e)}', 'error')

    return render_template('add_record.html', templates=templates)


@app.route('/add_template', methods=['GET', 'POST'])
def add_template():
    """添加食物模板"""
    if request.method == 'POST':
        try:
            # 验证比例总和不超过100%
            carb_ratio = float(request.form['carb_ratio'])
            protein_ratio = float(request.form['protein_ratio'])
            fat_ratio = float(request.form['fat_ratio'])

            total_ratio = carb_ratio + protein_ratio + fat_ratio
            if total_ratio > 100:
                flash('营养比例总和不能超过100%！', 'error')
                return render_template('add_template.html')

            template = FoodTemplate(
                name=request.form['name'],
                carb_ratio=carb_ratio,
                protein_ratio=protein_ratio,
                fat_ratio=fat_ratio
            )

            if request.form.get('calories'):
                template.calories = float(request.form['calories'])

            db.session.add(template)
            db.session.commit()
            flash('模板添加成功！', 'success')
            return redirect(url_for('templates'))
        except ValueError:
            flash('请输入有效的数字！', 'error')
        except Exception as e:
            flash(f'添加失败: {str(e)}', 'error')

    return render_template('add_template.html')


@app.route('/templates')
def templates():
    """查看所有模板"""
    templates = FoodTemplate.query.order_by(FoodTemplate.name).all()
    return render_template('templates.html', templates=templates)


@app.route('/history')
def history():
    """历史记录"""
    # 获取日期参数
    selected_date = request.args.get('date')
    if selected_date:
        try:
            target_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    # 获取该日期的所有记录
    records = DailyRecord.query.filter_by(date=target_date).order_by(DailyRecord.time.desc()).all()

    # 计算每日汇总
    daily_summary = NutrientCalculator.get_daily_summary(target_date)

    # 获取用户配置来计算目标
    user_config = UserConfig.query.first()
    goals = NutrientCalculator.calculate_daily_goals(user_config)

    return render_template('history.html',
                           records=records,
                           daily_summary=daily_summary,
                           goals=goals,
                           selected_date=target_date)


@app.route('/api/progress')
def api_progress():
    """API: 获取进度数据（用于AJAX更新）"""
    user_config = UserConfig.query.first()
    daily_summary = NutrientCalculator.get_daily_summary()
    progress = NutrientCalculator.get_progress(user_config, daily_summary)

    return jsonify(progress)


@app.route('/delete_record/<int:id>')
def delete_record(id):
    """删除记录"""
    record = DailyRecord.query.get_or_404(id)
    db.session.delete(record)
    db.session.commit()
    flash('记录已删除！', 'success')
    return redirect(url_for('index'))


@app.route('/delete_template/<int:id>')
def delete_template(id):
    """删除模板"""
    template = FoodTemplate.query.get_or_404(id)
    db.session.delete(template)
    db.session.commit()
    flash('模板已删除！', 'success')
    return redirect(url_for('templates'))


@app.route('/edit_template/<int:id>', methods=['GET', 'POST'])
def edit_template(id):
    """编辑模板"""
    template = FoodTemplate.query.get_or_404(id)

    if request.method == 'POST':
        try:
            template.name = request.form['name']
            template.carb_ratio = float(request.form['carb_ratio'])
            template.protein_ratio = float(request.form['protein_ratio'])
            template.fat_ratio = float(request.form['fat_ratio'])

            if request.form.get('calories'):
                template.calories = float(request.form['calories'])

            db.session.commit()
            flash('模板已更新！', 'success')
            return redirect(url_for('templates'))
        except Exception as e:
            flash(f'更新失败: {str(e)}', 'error')

    return render_template('edit_template.html', template=template)


# ========== 辅助函数 ==========
def generate_progress_chart(progress):
    """生成进度条图表"""
    try:
        # 准备数据
        labels = ['碳水', '蛋白质', '脂肪']
        percentages = [progress['carb']['percentage'],
                       progress['protein']['percentage'],
                       progress['fat']['percentage']]

        # 设置颜色：超标显示红色，未超标显示绿色
        colors = []
        for nutrient in ['carb', 'protein', 'fat']:
            if progress[nutrient]['is_over']:
                colors.append('#FF6B6B')  # 红色
            else:
                colors.append('#4ECDC4')  # 青色

        # 创建图表
        fig, ax = plt.subplots(figsize=(10, 4))
        bars = ax.bar(labels, percentages, color=colors)

        # 设置图表属性
        ax.set_ylim(0, 110)
        ax.set_ylabel('完成度 (%)')
        ax.set_title('今日营养素摄入进度')
        ax.axhline(y=100, color='red', linestyle='--', alpha=0.5)  # 100%参考线

        # 在每个柱子上添加数值标签
        for bar, percentage in zip(bars, percentages):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2., height + 2,
                    f'{percentage:.1f}%', ha='center', va='bottom', fontsize=10)

        # 转换为base64图像
        img = io.BytesIO()
        plt.tight_layout()
        plt.savefig(img, format='png', dpi=80, bbox_inches='tight')
        plt.close()
        img.seek(0)

        return base64.b64encode(img.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"生成图表失败: {e}")
        return None


# ========== 启动应用 ==========
if __name__ == '__main__':
    # 初始化数据库
    init_database()

    # 创建templates文件夹（如果不存在）
    if not os.path.exists('templates'):
        os.makedirs('templates')

    print("饮食追踪器启动中...")
    print("访问地址: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)