# 第九部分：Claude Code开发执行规范

------

# 80. Claude Code角色定义

你是一名：

> 资深AI应用全栈工程师，负责开发 TravelMind-Agent 智能旅游规划系统。

你的任务：

根据本PDR文档，实现一个完整可运行的AI Agent Web Demo。

开发目标：

不是制作普通旅游网站，而是实现：

> 一个基于大语言模型、多Agent协作、RAG知识增强、多模态理解能力的AI旅游决策智能体。

------

# 81. 项目开发目标

## 81.1 最终交付目标

完成一个Web应用：

用户可以：

1.  输入旅游需求； 
2.  AI理解用户偏好； 
3.  AI搜索旅游知识； 
4.  AI推荐适合地点； 
5.  AI自动生成旅游路线； 
6.  用户上传旅游图片； 
7.  AI识别图片并进行介绍。 

------

# 81.2 核心用户流程

完整流程：



```
用户输入需求

↓

User Profile Agent

↓

Orchestrator Agent任务分配

↓

Recommendation Agent

↓

RAG Knowledge Retrieval

↓

Planning Agent

↓

LLM生成旅行方案

↓

Frontend展示
```



------

# 82. 开发技术栈约束

## 82.1 前端技术

必须使用：

-  React 
-  TypeScript 
-  Vite 

UI：

推荐：

-  Tailwind CSS 
-  shadcn/ui 

要求：

-  页面简洁； 
-  支持聊天交互； 
-  支持卡片展示； 
-  支持图片上传。 

------

# 82.2 后端技术

必须使用：

Python

框架：

FastAPI

要求：

-  REST API； 
-  模块化结构； 
-  异步支持。 

------

# 82.3 AI技术

核心：

LLM API。

支持：

-  OpenAI API； 
-  Claude API； 
-  通义千问； 
-  DeepSeek。 

通过统一接口封装。

------

# 82.4 Agent框架

采用：

LangGraph。

实现：

多Agent状态流转。

------

# 82.5 数据库

业务数据库：

PostgreSQL。

ORM：

SQLAlchemy。

------

# 82.6 向量数据库

开发阶段：

优先：

Chroma。

后续：

FAISS。

------

# 83. 项目目录规范

Claude Code必须按照以下结构创建项目：



```
TravelMind-Agent/

├── frontend/

│
├── backend/

│
├── data/

│
├── docs/

│
├── README.md

└── .env.example
```



------

# 84. Backend详细结构要求



```
backend/

├── main.py


├── config/

│
└── settings.py


├── api/

│
├── chat.py

├── recommend.py

├── itinerary.py

└── image.py


├── agents/


│
├── orchestrator.py

├── profile_agent.py

├── trend_agent.py

├── recommendation_agent.py

├── planning_agent.py

└── vision_agent.py


├── rag/


│
├── embedding.py

├── retriever.py

└── vector_store.py


├── database/


│
├── models.py

├── database.py

└── schema.py


├── services/


│
├── llm_service.py

└── vision_service.py


└── utils/
```



------

# 85. Agent模块开发要求

------

# 85.1 Orchestrator Agent

文件：



```
agents/orchestrator.py
```



职责：

负责任务分配。

输入：

用户需求。

输出：

任务计划。

示例：

输入：



```
帮我规划重庆三日游
```



输出：



```
{
"tasks":[

"profile",

"recommend",

"planning"

]
}
```



------

# 85.2 User Profile Agent

文件：



```
profile_agent.py
```



职责：

提取用户旅游画像。

输入：

自然语言。

输出：



```
{
"destination":

"重庆",

"budget":

1500,

"duration":

3,

"interest":[

"摄影",

"美食"

]
}
```



------

# 85.3 Trend Agent

文件：



```
trend_agent.py
```



职责：

分析旅游趋势。

输入：

地点数据。

输出：

趋势评分。

示例：



```
{
"name":

"鹅岭二厂",

"trend_score":

92
}
```



------

# 85.4 Recommendation Agent

文件：



```
recommendation_agent.py
```



职责：

完成旅游地点排序。

输入：

用户画像。

候选地点。

输出：

推荐列表。

必须使用评分模型：



```
Score =
Preference
+
Trend
+
Budget
+
Location
+
Context
```



禁止：

直接随机推荐。

------

# 85.5 Planning Agent

文件：



```
planning_agent.py
```



职责：

生成旅行路线。

输入：

推荐地点。

输出：

每日计划。

格式：



```
{
"day1":[

"解放碑",

"洪崖洞"

],

"day2":[

"鹅岭二厂"

]
}
```



------

# 85.6 Vision Agent

文件：



```
vision_agent.py
```



职责：

图片理解。

输入：

用户图片。

输出：



```
{
"location":

"广州沙面",

"description":

"欧式建筑群",

"tags":[

"摄影"

]
}
```



------

# 86. RAG模块开发要求

目录：



```
rag/
```



------

# 86.1 数据加载

读取：



```
data/
```



中的旅游知识。

支持：

JSON。

------

# 86.2 文档处理

流程：



```
JSON

↓

Document

↓

Embedding

↓

Vector Store
```



------

# 86.3 检索流程

用户问题：

↓

Embedding

↓

Top-K搜索

↓

返回相关旅游知识

↓

LLM生成回答

------

# 87. 数据文件规范

禁止：

代码内写死数据。

错误：



```
places=[
"洪崖洞",
"解放碑"
]
```



正确：



```
data/attractions.json
```



示例：



```
[
{
"name":

"洪崖洞",

"city":

"重庆",

"tags":[

"夜景",

"摄影"

],

"price":

0
}
]
```



------

# 88. API开发规范

所有接口：

统一前缀：



```
/api/v1
```



------

## Chat接口

POST:



```
/api/v1/chat
```



功能：

AI对话。

------

## 推荐接口

POST:



```
/api/v1/recommend
```



功能：

生成推荐列表。

------

## 行程接口

POST:



```
/api/v1/itinerary/generate
```



功能：

生成旅行计划。

------

## 图片接口

POST:



```
/api/v1/image/analyze
```



功能：

图片识别。

------

# 89. 前端页面要求

至少实现以下页面：

------

# 页面1：首页

功能：

旅游AI助手入口。

包含：

-  输入框； 
-  示例问题。 

------

# 页面2：AI聊天页

展示：

用户问题。

AI回复。

------

# 页面3：推荐结果页

展示：

景点卡片。

包含：

-  图片； 
-  名称； 
-  标签； 
-  推荐理由； 
-  评分。 

------

# 页面4：旅行计划页

展示：

时间轴。

例如：

Day1

上午：

xxx

下午：

xxx

------

# 页面5：图片识别页

支持：

上传图片。

展示：

AI分析结果。

------

# 90. 开发优先级

必须按照以下顺序：

------

## Phase 1

基础工程

完成：

-  React初始化； 
-  FastAPI启动； 
-  前后端连接。 

------

## Phase 2

LLM能力

完成：

-  Chat API； 
-  LLM调用封装。 

------

## Phase 3

Agent系统

完成：

-  Orchestrator； 
-  Profile Agent； 
-  Recommendation Agent； 
-  Planning Agent。 

------

## Phase 4

RAG

完成：

-  数据加载； 
-  Embedding； 
-  检索。 

------

## Phase 5

多模态

完成：

-  图片上传； 
-  Vision API。 

------

## Phase 6

优化展示

完成：

-  UI优化； 
-  Demo流程。 

------

# 91. Claude Code禁止事项

开发过程中禁止：

## 1.

不要创建复杂爬虫系统。

原因：

不符合14天开发周期。

------

## 2.

不要训练模型。

使用已有模型API。

------

## 3.

不要过度设计微服务。

保持单体应用。

------

## 4.

不要提前开发：

-  地图导航； 
-  支付； 
-  用户社交； 
-  视频理解。 

------

## 5.

不要生成无法运行的伪代码。

所有代码：

必须：

-  可运行； 
-  有依赖； 
-  有启动方式。 

------

# 92. 开发完成标准

项目完成后必须满足：

## 功能

✅ 用户输入旅游需求

✅ AI理解需求

✅ RAG检索知识

✅ 推荐地点

✅ 自动规划路线

✅ 图片识别

------

## 技术

✅ React

✅ FastAPI

✅ LLM

✅ Multi-Agent

✅ RAG

✅ PostgreSQL

------

## 展示

能够完成：

一次完整旅游规划流程。