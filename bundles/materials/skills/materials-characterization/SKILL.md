# SKILL: materials-characterization（材料表征）

> 学科包 materials 的表征方法约束。覆盖 XRD / 电子显微 / 光谱 / 比表面等常用表征的
> 报告规范与不确定性要求。升级到 L1（含 `scripts/validate_report.py` 确定性校验）。

## 触发条件
当执行以下任务时自动激活：
- 处理 XRD / SEM / TEM / XPS / Raman / BET / DSC-TGA 等表征数据
- 计算晶格参数、晶粒尺寸（Scherrer）、带隙（Tauc）、比表面积（BET）
- 报告材料合成—结构—性能关系中的量化指标
- 撰写论文的 Results / Characterization 章节
- 复核实验失败归因（METH 类：样品不一致 / 测量不确定度不足）

## 方法论约束（必须遵守）
1. 任何量化指标必须报告不确定度（标准偏差 / 标准误），禁止只报单点值
2. 重复测量样本量 n ≥ 3，并报告 n 与重复方式（平行样 / 多次扫描）
3. 单位必须显式标注（nm、cm²/g、eV、° 等），不得隐式省略
4. 仪器型号、测试条件（加速电压、扫描速率、光源）须随数据记录（可复现性）
5. XRD 物相鉴定须给出检索依据（PDF 卡片号 / ICDD），不得仅凭峰位臆断
6. Scherrer 公式晶粒尺寸须说明 K 值与衍射峰展宽扣除方式（仪器宽化）
7. Tauc 带隙须说明跃迁类型（direct / indirect）与线性外推依据
8. BET 比表面积须说明相对压力范围（如 0.05–0.30 P/P₀）与多点/单点法
9. 所有数值结论须由 sidecar 工具或独立脚本计算，模型不得自行给出数值
10. 样品批次不一致导致的差异，须显式区分"工艺效应"与"批次效应"

## 输出 Schema
```json
{
  "sample_id": "M-001",
  "method": "xrd",
  "crystal_phase": "anatase",
  "pdf_card": "21-1272",
  "value": 12.4,
  "uncertainty": 0.6,
  "unit": "nm",
  "instrument": "Rigaku SmartLab",
  "n_repeats": 3,
  "source_tool": "bundles.materials.skills.materials_characterization.scripts.validate_report"
}
```

## 参考文件
- IUPAC 物理化学量与符号规范
- ISO 9277（BET 比表面积测定）
- ./references/materials_terminology.json

## 注意事项
- 禁止用单次测量值代表批次性能
- 禁止对未扣除仪器宽化的 XRD 峰直接套用 Scherrer 公式
- 数值一致性：与原始数据文件比对须完全一致（容差 1e-6）
