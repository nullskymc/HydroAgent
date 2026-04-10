# SmartIrrigation 天气查询模块使用文档

当前项目默认使用 [Open-Meteo](https://open-meteo.com/) 作为天气服务：

- 免费
- 默认无需 API Key
- 支持地名查询和多日预报

## 配置说明

默认情况下不需要配置天气 Key，只需要保留或设置天气接口地址：

```yaml
apis:
  weather_service_url: "https://api.open-meteo.com/v1/forecast"
```

如果你想走自建代理，也可以通过环境变量覆盖：

```bash
export API_SERVICE_URL="https://your-proxy.example.com/v1/forecast"
```

## 使用方式

### 在代码中使用

```python
from src.data.data_processing import DataProcessingModule

data_processor = DataProcessingModule()

# 兼容旧调用方式：传城市编码
weather_data = data_processor.get_weather_data("110000")

# 推荐：传城市名
weather_data = data_processor.get_weather_by_city_name("北京")
```

### 返回结构

为了兼容现有前端和工具链，模块仍然返回旧字段风格：

```python
{
    "adcode": "110000",
    "city": "北京",
    "province": "北京市",
    "location": "北京",
    "timestamp": "2026-04-04T08:00:00",
    "temperature": 22.5,
    "humidity": 65.0,
    "wind_speed": 3.2,
    "condition": "晴",
    "precipitation": 0.0,
    "lives": {
        "province": "北京市",
        "city": "北京",
        "adcode": "110000",
        "weather": "晴",
        "temperature": "22.5",
        "winddirection": "东南",
        "windpower": "3.2m/s",
        "humidity": "65",
        "reporttime": "2026-04-04T08:00:00"
    },
    "forecast": [
        {
            "date": "2026-04-04",
            "dayweather": "晴",
            "nightweather": "晴",
            "daytemp": "28",
            "nighttemp": "18",
            "daywind": "东南",
            "nightwind": "东南",
            "daypower": "3.2m/s",
            "nightpower": "3.2m/s"
        }
    ]
}
```

## 技术说明

项目内部会分两步请求：

1. 调用 Open-Meteo Geocoding API，把城市名转成经纬度
2. 调用 Open-Meteo Forecast API 获取当前天气和未来 4 天预报

官方文档：

- [Open-Meteo Weather Forecast API](https://open-meteo.com/en/docs)
- [Open-Meteo Geocoding API](https://open-meteo.com/en/docs/geocoding-api)
