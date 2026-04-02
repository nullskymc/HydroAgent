"""
数据库模块的测试
"""
import unittest
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, SensorData, WeatherData, IrrigationLog, User
from src.database.models import create_item, get_item, get_items, update_item, delete_item
from src.exceptions import DatabaseError
from datetime import datetime

class TestDatabaseModels(unittest.TestCase):
    """测试数据库模型和CRUD操作"""
    
    @classmethod
    def setUpClass(cls):
        """建立内存数据库连接"""
        cls.engine = create_engine('sqlite:///:memory:')
        cls.SessionLocal = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(cls.engine)
    
    @classmethod
    def tearDownClass(cls):
        """清理资源"""
        Base.metadata.drop_all(cls.engine)
    
    def setUp(self):
        """每个测试前建立会话"""
        self.db = self.SessionLocal()
    
    def tearDown(self):
        """每个测试后清理会话"""
        self.db.close()
    
    def test_sensor_data_model(self):
        """测试传感器数据模型"""
        now = datetime.utcnow()
        sensor_data = SensorData(
            sensor_id="test-sensor-001",
            timestamp=now,
            soil_moisture=45.5,
            temperature=22.3,
            light_intensity=850,
            rainfall=0.2,
            raw_data={"some": "data"}
        )
        
        self.db.add(sensor_data)
        self.db.commit()
        
        # 验证记录已保存并且ID已分配
        self.assertIsNotNone(sensor_data.id)
        
        # 查询验证
        retrieved = self.db.query(SensorData).filter_by(sensor_id="test-sensor-001").first()
        self.assertEqual(retrieved.soil_moisture, 45.5)
        self.assertEqual(retrieved.temperature, 22.3)
    
    def test_weather_data_model(self):
        """测试天气数据模型"""
        now = datetime.utcnow()
        weather_data = WeatherData(
            location="Tokyo",
            timestamp=now,
            temperature=25.0,
            humidity=60.0,
            wind_speed=3.5,
            condition="Clear",
            precipitation=0.0,
            forecast_data={"forecast": "data"}
        )
        
        self.db.add(weather_data)
        self.db.commit()
        
        # 验证记录已保存
        retrieved = self.db.query(WeatherData).filter_by(location="Tokyo").first()
        self.assertEqual(retrieved.temperature, 25.0)
        self.assertEqual(retrieved.condition, "Clear")
    
    def test_irrigation_log_model(self):
        """测试灌溉日志模型"""
        now = datetime.utcnow()
        log = IrrigationLog(
            event="start",
            start_time=now,
            end_time=now,
            duration_planned_seconds=1800,
            duration_actual_seconds=1750,
            status="completed",
            message="正常完成灌溉"
        )
        
        self.db.add(log)
        self.db.commit()
        
        # 验证记录已保存
        retrieved = self.db.query(IrrigationLog).filter_by(status="completed").first()
        self.assertEqual(retrieved.event, "start")
        self.assertEqual(retrieved.duration_planned_seconds, 1800)
    
    def test_user_model(self):
        """测试用户模型"""
        user = User(
            username="testuser",
            password_hash="hashedpassword123",
            email="test@example.com",
            is_active=True,
            is_admin=False
        )
        
        self.db.add(user)
        self.db.commit()
        
        # 验证记录已保存
        retrieved = self.db.query(User).filter_by(username="testuser").first()
        self.assertEqual(retrieved.email, "test@example.com")
        self.assertTrue(retrieved.is_active)
        self.assertFalse(retrieved.is_admin)
    
    def test_crud_operations(self):
        """测试CRUD操作函数"""
        # 测试创建
        sensor_data = create_item(
            self.db, 
            SensorData, 
            sensor_id="test-crud",
            timestamp=datetime.utcnow(),
            soil_moisture=50.0,
            temperature=20.0
        )
        self.assertIsNotNone(sensor_data.id)
        
        # 测试读取
        retrieved = get_item(self.db, SensorData, sensor_data.id)
        self.assertEqual(retrieved.sensor_id, "test-crud")
        
        # 测试更新
        updated = update_item(self.db, SensorData, sensor_data.id, soil_moisture=55.0)
        self.assertEqual(updated.soil_moisture, 55.0)
        
        # 测试列表查询
        items = get_items(self.db, SensorData, sensor_id="test-crud")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, sensor_data.id)
        
        # 测试删除
        deleted = delete_item(self.db, SensorData, sensor_data.id)
        self.assertEqual(deleted.id, sensor_data.id)
        
        # 验证已删除
        self.assertIsNone(get_item(self.db, SensorData, sensor_data.id))
    
    @patch('src.database.models.Base.metadata.create_all')
    def test_init_db_error(self, mock_create_all):
        """测试数据库初始化错误处理"""
        from src.database.models import init_db
        
        # 模拟创建失败
        mock_create_all.side_effect = Exception("Test DB initialization error")
        
        # 验证异常传递
        with self.assertRaises(DatabaseError):
            init_db()

if __name__ == "__main__":
    unittest.main()
