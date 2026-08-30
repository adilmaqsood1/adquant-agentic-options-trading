from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class ParameterSchema(BaseModel):
    key: str
    label: str
    type: str
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    options: Optional[List[str]] = None


class StrategyMetadata(BaseModel):
    id: str
    strategy: str
    asset_class: str
    default_symbol: str
    type: str
    description: str
    universe_symbols: List[str]
    parameters: List[ParameterSchema]


class UniverseMetadata(BaseModel):
    id: str
    label: str
    market: str
    symbols: List[str]


class BacktestRunRequest(BaseModel):
    strategy: str
    symbols: List[str] = Field(default_factory=list)
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    lookbackDays: Optional[int] = 252
    skipRecentDays: Optional[int] = 21
    portfolioSize: int = 10
    initialCapital: float = 100000.0
    benchmark: str = "SPY"
    strategyParams: Dict[str, Any] = Field(default_factory=dict)


class ConditionSchema(BaseModel):
    id: Optional[str] = None
    indicator: str
    operator: str
    value: str
    logic: str = "AND"


class RuleSchema(BaseModel):
    id: Optional[str] = None
    name: str
    type: str  # 'entry' or 'exit'
    action: str = "buy"
    qty: Any = 100
    conditions: List[ConditionSchema] = Field(default_factory=list)


class CustomStrategyBacktestRequest(BaseModel):
    name: str
    rules: List[RuleSchema]
    symbols: List[str] = Field(default_factory=list)
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    initialCapital: float = 100000.0
    portfolioSize: int = 10
    benchmark: str = "SPY"


class PerformanceMetrics(BaseModel):
    totalReturn: float
    annualizedReturn: float
    benchmarkReturn: float
    benchmarkAnnualizedReturn: float
    sharpeRatio: float
    sortinoRatio: float
    maxDrawdown: float
    winRate: float
    profitFactor: float
    volatility: float
    calmarRatio: float
    totalTrades: int


class ChartPoint(BaseModel):
    date: str
    strategy: float
    benchmark: float


class TradeItem(BaseModel):
    id: int
    symbol: str
    entryDate: str
    exitDate: Optional[str] = None
    entryPrice: float
    exitPrice: Optional[float] = None
    returnPct: Optional[float] = None
    pnl: Optional[float] = None
    status: str


class BacktestResponse(BaseModel):
    runId: str
    runDurationMs: int
    config: Dict[str, Any]
    metrics: PerformanceMetrics
    chartData: List[ChartPoint]
    trades: List[TradeItem]
