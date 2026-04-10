# HydroAgent 天气模块说明

天气模块为灌溉计划提供近期天气风险信息，重点用于判断未来 48 小时是否存在降雨，从而影响 `start` 或 `hold` 计划。

## 当前实现

- 默认天气服务地址来自 `config.yaml` 或环境变量 `API_SERVICE_URL`。
- 当前默认使用 Open-Meteo 形式的天气查询能力，不需要 API Key。
- 模块保留对旧高德天气数据结构的兼容处理，便于历史测试和后续替换。
- 如果天气服务不可用，计划服务会生成离线兜底摘要，保证灌溉计划流程继续运行并保持保守决策。

## 配置示例

```yaml
apis:
  weather_api_key: ""
  weather_service_url: "https://api.open-meteo.com/v1/forecast"
```

也可以通过环境变量覆盖：

```bash
API_SERVICE_URL=https://api.open-meteo.com/v1/forecast
WEATHER_API_KEY=
```

## 在项目中使用

```python
from src.data.data_processing import DataProcessingModule

data_processor = DataProcessingModule()
weather = data_processor.get_weather_by_city_name("北京")
print(weather.get("city"))
print(weather.get("forecast", []))
```

在主业务链路中，`src/services/irrigation_service.py` 会调用天气模块生成 `weather_summary`。如果未来 48 小时存在降雨且土壤湿度没有进入紧急区间，系统会建议暂缓灌溉。

## 毕设表述建议

论文中建议描述为：

```text
系统通过天气模块获取近期天气预报，并将降雨信号作为灌溉计划安全审查的一部分。当天气数据不可用时，系统采用保守兜底策略，避免因外部服务异常导致计划链路中断。
```

不要把当前实现描述为“已稳定接入生产级气象平台”。如果答辩需要展示真实天气数据，应提前确认网络环境和接口可用性。
