import { useEffect, useMemo, useState } from 'react';
import { SchedulingManagement } from './SchedulingManagement';

const REPORT_TYPES = [
  '人行大集中报送', '资管产品模板逐笔', '1104报送', '21/23版全要素报送',
  '中信登定期报送', 'EAST5.0报送', '五篇大文章报送',
];

const INITIAL_JOBS = [
  ['监管报送集市生成', '成功', 100, '2026-09-08 10:13:21', '00:01:28'],
  ['人行明细表：贷款信息', '成功', 100, '2026-09-08 10:14:49', '00:02:15'],
  ['人行明细表：科目信息', '成功', 100, '2026-09-08 10:17:04', '00:01:52'],
  ['人行结果表：表2-1资产负债明细模板', '成功', 100, '2026-09-08 10:18:56', '00:00:46'],
];

const RULES = [
  ['1104-A001', '关联方注册地区代码规范性校验', '不通过', 36, '00:01:12'],
  ['1104-A002', '客户证件号码完整性校验', '不通过', 12, '00:00:48'],
  ['1104-A003', '机构名称与统一社会信用代码一致性', '通过', 0, '00:01:06'],
  ['1104-B011', '贷款余额与明细汇总勾稽校验', '通过', 0, '00:02:31'],
  ['1104-B018', '五级分类代码有效性校验', '不通过', 8, '00:00:36'],
  ['1104-C006', '表内外业务余额跨表一致性校验', '通过', 0, '00:01:45'],
];

const ERROR_DETAILS = [
  ['FR-209', '徐工集团工程机械股份有限公司', '9132030013479342XH', '320371', '江苏省徐州经济技术开发区驮蓝山路26号'],
  ['FR-429', '江苏苏豪金属有限公司', '91320281690278071M', '320371', '徐州经济技术开发区金山桥工业园'],
  ['FR-205', '苏州中方财团控股股份有限公司', '91320000134788401D', '320571', '苏州工业园区置业商务广场'],
  ['FR-151', '华能（苏州工业园区）发电有限责任公司', '91320594134849783B', '320571', '中国（江苏）自由贸易试验区苏州片区'],
  ['FR-204', '苏州元禾控股股份有限公司', '91320000666820365U', '320571', '苏州工业园区苏虹东路183号'],
];

function Status({ value }) {
  const kind = value === '成功' || value === '通过' || value === '已完成' ? 'success'
    : value === '运行中' || value === '校验中' ? 'running'
      : value === '等待' ? 'muted' : 'danger';
  return <span className={`status status-${kind}`}><i />{value}</span>;
}

function AppHeader({ activeModule, scheduleSection, onNavigate, onNavigateSchedule }) {
  const [scheduleMenuOpen, setScheduleMenuOpen] = useState(false);
  const navItems = ['报送导航', '智能核数', '报送管理'];
  const endNavItems = ['工具', '系统管理'];
  return (
    <header className="app-header">
      <div className="brand"><img src="/logo-full.svg" alt="监管智核" /><strong>监管智核</strong><span>金融监管数据报送平台</span><b>V1.2</b></div>
      <nav className="global-nav" aria-label="系统导航">
        {navItems.map(item => <button key={item} className={activeModule === item ? 'active' : ''} onClick={() => onNavigate(item)}>{item}</button>)}
        <div className={`global-nav-group ${scheduleMenuOpen ? 'open' : ''}`} onMouseEnter={() => setScheduleMenuOpen(true)} onMouseLeave={() => setScheduleMenuOpen(false)}>
          <button className={activeModule === '调度管理' ? 'active' : ''} aria-haspopup="menu" aria-expanded={scheduleMenuOpen} onClick={() => setScheduleMenuOpen(true)}>调度管理</button>
          <div className="global-submenu" role="menu" aria-label="调度管理二级菜单">
            {['KETTLE', '版本管理', '定时调度'].map(item => <button key={item} role="menuitem" className={scheduleSection === item ? 'current' : ''} onClick={() => { onNavigateSchedule(item); setScheduleMenuOpen(false); }}>{item}<span>{item === 'KETTLE' ? '在线设计' : item === '版本管理' ? '版本与发布' : '生产任务'}</span></button>)}
          </div>
        </div>
        {endNavItems.map(item => <button key={item} className={activeModule === item ? 'active' : ''} onClick={() => onNavigate(item)}>{item}</button>)}
      </nav>
      <div className="account"><span>2026-09-08</span><span>星期二</span><i /><span className="avatar">张</span><strong>张三</strong><span>监管机构</span></div>
    </header>
  );
}

function ReportRail({ selected, onSelect }) {
  return <aside className="report-rail"><div className="rail-title">报送类型</div>{REPORT_TYPES.map(item => <button key={item} className={selected === item ? 'active' : ''} onClick={() => onSelect(item)}>{item}</button>)}</aside>;
}

function PageToolbar({ period, setPeriod, children }) {
  return <div className="page-toolbar"><label><span>报送期</span><input type="date" value={period} onChange={e => setPeriod(e.target.value)} /></label><div className="toolbar-actions">{children}</div></div>;
}

function MessageModal({ onClose, onGenerate }) {
  const [selected, setSelected] = useState([true, true, true, true]);
  const files = ['G01_资产负债项目统计表', 'G04_利润表', 'G12_贷款质量迁徙情况表', 'G14_大额风险暴露统计表'];
  return <div className="modal-mask" role="dialog" aria-modal="true"><div className="modal">
    <div className="modal-head"><div><h3>生成最新报文</h3><p>以本报送期最新一次成功生成的报表为基础</p></div><button className="text-btn" onClick={onClose}>关闭</button></div>
    <div className="modal-context"><span>报送类型</span><strong>1104报送</strong><span>报送期</span><strong>2026-08-31</strong></div>
    <div className="modal-list"><div className="modal-list-head">选择需要生成的报文</div>{files.map((file, index) => <label key={file}><input type="checkbox" checked={selected[index]} onChange={() => setSelected(old => old.map((value, i) => i === index ? !value : value))} /><span>{file}</span><em>XML</em></label>)}</div>
    <div className="notice">生成报文不会自动执行校验，也不会覆盖此前已生成的报文文件。</div>
    <div className="modal-actions"><button className="secondary" onClick={onClose}>取消</button><button className="primary" onClick={() => onGenerate(selected.filter(Boolean).length)}>生成所选报文</button></div>
  </div></div>;
}

function GenerationPage({ reportType, period, setPeriod, notify }) {
  const [autoValidate, setAutoValidate] = useState(false);
  const [running, setRunning] = useState(false);
  const [showMessageModal, setShowMessageModal] = useState(false);
  const [jobs, setJobs] = useState(INITIAL_JOBS);
  const [logs, setLogs] = useState([
    '10:18:56  [INFO]  报表生成流程执行完成', '10:18:32  [INFO]  已完成 G14 大额风险暴露统计表',
    '10:18:04  [INFO]  已完成 G12 贷款质量迁徙情况表', '10:17:36  [INFO]  已完成 G04 利润表',
    '10:17:12  [INFO]  已完成 G01 资产负债项目统计表', '10:13:21  [INFO]  加载报送期参数 2026-08-31',
  ]);
  const startGenerate = () => {
    if (running) return;
    setRunning(true);
    setJobs([['监管报送集市生成', '运行中', 64, '2026-09-08 14:26:08', '00:00:41'], ['人行明细表：贷款信息', '等待', 0, '-', '-'], ['人行明细表：科目信息', '等待', 0, '-', '-'], ['人行结果表：表2-1资产负债明细模板', '等待', 0, '-', '-']]);
    setLogs(['14:26:08  [INFO]  开始生成 1104 报表', '14:26:08  [INFO]  加载报送期参数 2026-08-31', '14:26:09  [INFO]  正在执行 监管报送集市生成']);
    notify('已提交报表生成任务，可在当前页面查看进度');
    window.setTimeout(() => { setRunning(false); setJobs(INITIAL_JOBS); setLogs(old => ['14:26:47  [INFO]  报表生成任务执行完成', ...(autoValidate ? ['14:26:47  [INFO]  已自动创建独立校验任务'] : []), ...old]); }, 1800);
  };
  const history = [
    ['2026-09-08 10:02:15', '2026-08-31', '成功', '18张报表', '4份报文', '张三'],
    ['2026-09-07 18:36:21', '2026-08-31', '成功', '18张报表', '未生成', '李四'],
    ['2026-09-07 10:14:08', '2026-08-31', '成功', '18张报表', '4份报文', '王五'],
    ['2026-09-06 19:22:37', '2026-07-31', '成功', '18张报表', '4份报文', '赵六'],
  ];
  return <>
    <PageToolbar period={period} setPeriod={setPeriod}><label className="auto-check"><input type="checkbox" checked={autoValidate} onChange={e => setAutoValidate(e.target.checked)} /><span>生成完成后自动执行校验</span></label><button className="secondary" onClick={() => setShowMessageModal(true)}>生成最新报文</button><button className="primary" onClick={startGenerate}>{running ? '生成中…' : '生成报表'}</button></PageToolbar>
    <div className="context-strip"><span>当前报送</span><strong>{reportType}</strong><i /><span>报送期</span><strong>{period}</strong><i /><span>本次只生成报表，不自动生成报文文件</span></div>
    <div className="execution-grid">
      <section className="panel jobs-panel"><div className="panel-head"><div><h3>Kettle作业执行顺序</h3><p>报表生成流程</p></div><Status value={running ? '运行中' : '已完成'} /></div><table><thead><tr><th>序号</th><th>作业名称</th><th>状态</th><th>执行进度</th><th>开始时间</th><th>耗时</th></tr></thead><tbody>{jobs.map((row, index) => <tr key={row[0]}><td>{index + 1}</td><td className="strong-cell">{row[0]}</td><td><Status value={row[1]} /></td><td><div className="progress-wrap"><div className="progress"><i style={{ width: `${row[2]}%` }} /></div><span>{row[2]}%</span></div></td><td>{row[3]}</td><td>{row[4]}</td></tr>)}</tbody></table></section>
      <section className="panel log-panel"><div className="panel-head"><div><h3>实时执行日志</h3><p>当前任务输出</p></div><button className="text-btn" onClick={() => setLogs([])}>清空</button></div><div className="logs">{logs.length ? logs.map(line => <p key={line}>{line}</p>) : <div className="empty">暂无日志</div>}</div></section>
    </div>
    <section className="panel history-panel"><div className="panel-head"><div><h3>最近生成记录</h3><p>生成记录独立保存；历史报送期仅支持查看和下载</p></div><button className="text-btn" onClick={() => notify('记录已刷新')}>刷新</button></div><table><thead><tr><th>执行时间</th><th>报送期</th><th>执行结果</th><th>生成报表</th><th>报文文件</th><th>操作人</th><th>操作</th></tr></thead><tbody>{history.map((row, index) => <tr key={row[0]}><td>{row[0]}</td><td>{row[1]}</td><td><Status value={row[2]} /></td><td>{row[3]}</td><td><span className={row[4] === '未生成' ? 'muted-text' : 'file-count'}>{row[4]}</span></td><td>{row[5]}</td><td className="actions"><button onClick={() => notify('已打开本次报表生成日志')}>查看日志</button>{index < 3 && <button onClick={() => setShowMessageModal(true)}>{row[4] === '未生成' ? '生成报文' : '重新生成报文'}</button>}{row[4] !== '未生成' && <button onClick={() => notify('已开始下载报文压缩包')}>下载报文</button>}</td></tr>)}</tbody></table></section>
    {showMessageModal && <MessageModal onClose={() => setShowMessageModal(false)} onGenerate={count => { setShowMessageModal(false); notify(`已提交 ${count} 份报文生成任务`); }} />}
  </>;
}

function ValidationDetail({ onClose }) {
  return <div className="modal-mask" role="dialog" aria-modal="true"><div className="modal wide-modal">
    <div className="modal-head"><div><h3>错误明细 · 关联方注册地区代码规范性校验</h3><p>规则 1104-A001 · 共 36 条错误数据</p></div><button className="text-btn" onClick={onClose}>关闭</button></div>
    <div className="detail-filter"><input placeholder="输入关联方名称或编号" /><button className="secondary">查询</button><button className="secondary">重置</button><span>列表字段根据校验 SQL 查询结果自动生成</span></div>
    <div className="table-scroll"><table><thead><tr><th>序号</th><th>关联方编号</th><th>关联方名称</th><th>关联方证件号码</th><th>注册地区代码</th><th>注册地址</th></tr></thead><tbody>{ERROR_DETAILS.map((row, index) => <tr key={row[0]}><td>{index + 1}</td>{row.map(cell => <td key={cell}>{cell}</td>)}</tr>)}</tbody></table></div>
    <div className="modal-footer-note">当前显示 1–5 条，共 36 条</div>
  </div></div>;
}

function ValidationPage({ reportType, period, setPeriod, notify }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const [validating, setValidating] = useState(false);
  const runValidation = () => { setValidating(true); notify('已创建一条新的独立校验记录'); window.setTimeout(() => setValidating(false), 1600); };
  return <>
    <PageToolbar period={period} setPeriod={setPeriod}><button className="primary" onClick={runValidation}>{validating ? '校验中…' : '开始校验'}</button></PageToolbar>
    <div className="context-strip"><span>当前报送</span><strong>{reportType}</strong><i /><span>报送期</span><strong>{period}</strong><i /><span>每次执行都会产生一条独立校验记录</span></div>
    <div className="metrics"><div><span>校验规则</span><strong>2,000</strong><small>本次规则总数</small></div><div><span>已完成</span><strong>2,000</strong><small>执行完成率 100%</small></div><div className="metric-success"><span>通过</span><strong>1,952</strong><small>97.6%</small></div><div className="metric-danger"><span>不通过</span><strong>48</strong><small>共发现 286 条错误</small></div><div><span>异常</span><strong>0</strong><small>SQL 执行异常</small></div></div>
    <section className="panel rules-panel"><div className="panel-head"><div><h3>本次校验结果</h3><p>执行时间 2026-09-08 11:26:32 · 操作人 张三 · 耗时 00:18:42</p></div><div className="filter-group"><input placeholder="规则编号或名称" /><select defaultValue="all"><option value="all">全部状态</option><option>不通过</option><option>通过</option></select><button className="secondary">查询</button></div></div><table><thead><tr><th>规则编号</th><th>校验规则</th><th>状态</th><th>错误条数</th><th>执行耗时</th><th>操作</th></tr></thead><tbody>{RULES.map(row => <tr key={row[0]}><td className="code-cell">{row[0]}</td><td className="strong-cell">{row[1]}</td><td><Status value={row[2]} /></td><td>{row[3] ? <button className="error-count" onClick={() => setDetailOpen(true)}>{row[3]}</button> : <span>0</span>}</td><td>{row[4]}</td><td className="actions"><button onClick={() => row[3] ? setDetailOpen(true) : notify('该规则没有错误明细')}>查看明细</button></td></tr>)}</tbody></table></section>
    <section className="panel history-panel compact-history"><div className="panel-head"><div><h3>历次校验记录</h3><p>同一报送期可以人工执行多次校验</p></div></div><table><thead><tr><th>执行时间</th><th>报送期</th><th>规则数</th><th>不通过规则</th><th>错误数据</th><th>操作人</th><th>操作</th></tr></thead><tbody><tr><td>2026-09-08 11:26:32</td><td>2026-08-31</td><td>2,000</td><td className="danger-text">48</td><td className="danger-text">286</td><td>张三</td><td className="actions"><button>查看结果</button></td></tr><tr><td>2026-09-08 09:48:15</td><td>2026-08-31</td><td>2,000</td><td className="danger-text">67</td><td className="danger-text">412</td><td>李四</td><td className="actions"><button>查看结果</button></td></tr><tr><td>2026-09-07 16:22:09</td><td>2026-08-31</td><td>2,000</td><td className="danger-text">83</td><td className="danger-text">631</td><td>张三</td><td className="actions"><button>查看结果</button></td></tr></tbody></table></section>
    {detailOpen && <ValidationDetail onClose={() => setDetailOpen(false)} />}
  </>;
}

function GenerationConfig() {
  return <div className="config-grid">
    <section className="panel form-panel"><div className="panel-head"><div><h3>报表输出设置</h3><p>定义报表生成位置和命名方式</p></div></div><div className="form-grid"><label><span>报表输出目录</span><input defaultValue="/data/report/1104/{report_period}/" /></label><label><span>报表文件命名</span><input defaultValue="{report_code}_{report_period}_{time}" /></label><label><span>报表文件格式</span><select defaultValue="xlsx"><option value="xlsx">Excel（.xlsx）</option><option>CSV</option></select></label><label><span>报文输出目录</span><input defaultValue="/data/message/1104/{report_period}/" /></label></div><div className="form-note">报表生成完成后不会自动产生报文文件；报文由生成记录中的“生成报文”操作单独触发。</div></section>
    <section className="panel form-panel"><div className="panel-head"><div><h3>报文清单</h3><p>配置允许单独生成的报文</p></div><button className="text-btn">新增报文</button></div><table><thead><tr><th>报文代码</th><th>报文名称</th><th>格式</th><th>启用</th><th>操作</th></tr></thead><tbody>{['G01|资产负债项目统计表|XML', 'G04|利润表|XML', 'G12|贷款质量迁徙情况表|XML', 'G14|大额风险暴露统计表|XML'].map(item => { const [code, name, type] = item.split('|'); return <tr key={code}><td className="code-cell">{code}</td><td>{name}</td><td>{type}</td><td><span className="switch on"><i /></span></td><td className="actions"><button>编辑</button></td></tr>; })}</tbody></table></section>
  </div>;
}

function KettleConfig() {
  return <div className="config-grid">
    <section className="panel form-panel"><div className="panel-head"><div><h3>Kettle服务连接</h3><p>调用生产服务器现有 API 执行作业并获取日志</p></div><button className="secondary">测试连接</button></div><div className="form-grid"><label className="span-two"><span>服务地址</span><input defaultValue="http://10.20.30.18:8080/kettle-api" /></label><label><span>接口用户名</span><input defaultValue="autocheck_service" /></label><label><span>接口密码</span><input type="password" defaultValue="123456789" /></label><label><span>连接超时</span><input defaultValue="30 秒" /></label><label><span>任务超时</span><input defaultValue="120 分钟" /></label></div></section>
    <section className="panel form-panel"><div className="panel-head"><div><h3>作业编排</h3><p>报表生成与报文生成使用不同的 Kettle 作业</p></div><button className="text-btn">新增作业</button></div><table><thead><tr><th>顺序</th><th>用途</th><th>KJB作业路径</th><th>失败处理</th><th>操作</th></tr></thead><tbody><tr><td>1</td><td>报表生成</td><td className="code-cell">/1104/report/report_generate.kjb</td><td>停止后续作业</td><td className="actions"><button>编辑</button></td></tr><tr><td>2</td><td>报文生成</td><td className="code-cell">/1104/message/message_generate.kjb</td><td>记录失败报文</td><td className="actions"><button>编辑</button></td></tr></tbody></table></section>
  </div>;
}

function SqlConfig({ notify }) {
  const [onlyEnabled, setOnlyEnabled] = useState(false);
  return <section className="panel rules-panel config-rules"><div className="panel-head"><div><h3>SQL校验规则</h3><p>共 2,000 条规则，支持按 SQL 查询字段自动展示错误明细列</p></div><div className="filter-group"><input placeholder="规则编号或名称" /><label className="inline-toggle"><input type="checkbox" checked={onlyEnabled} onChange={e => setOnlyEnabled(e.target.checked)} />仅看启用</label><button className="primary" onClick={() => notify('已打开新增校验规则表单')}>新增规则</button></div></div><table><thead><tr><th>规则编号</th><th>规则名称</th><th>SQL来源</th><th>错误明细字段</th><th>启用</th><th>操作</th></tr></thead><tbody>{RULES.slice(0, 5).map((row, index) => <tr key={row[0]}><td className="code-cell">{row[0]}</td><td>{row[1]}</td><td>{index % 2 ? 'SVN脚本' : '在线配置'}</td><td>{index === 0 ? '5个字段' : `${3 + index}个字段`}</td><td><span className="switch on"><i /></span></td><td className="actions"><button onClick={() => notify(`正在编辑规则 ${row[0]}`)}>编辑</button><button>查看SQL</button></td></tr>)}</tbody></table><div className="pagination"><span>共 2,000 条</span><button>上一页</button><button className="current">1</button><button>2</button><button>3</button><button>下一页</button></div></section>;
}

function ConfigPage({ reportType, notify }) {
  const [section, setSection] = useState('报表生成配置');
  return <><div className="config-heading"><div><h2>{reportType}</h2><p>配置按报送类型长期生效，不随报送期变化</p></div><button className="primary" onClick={() => notify(`${reportType}配置已保存`)}>保存配置</button></div><div className="config-tabs">{['报表生成配置', 'Kettle调度配置', 'SQL校验配置'].map(item => <button key={item} className={section === item ? 'active' : ''} onClick={() => setSection(item)}>{item}</button>)}</div>{section === '报表生成配置' && <GenerationConfig />}{section === 'Kettle调度配置' && <KettleConfig />}{section === 'SQL校验配置' && <SqlConfig notify={notify} />}</>;
}

function ReportingManagement({ notify }) {
  const [tab, setTab] = useState('报表生成');
  const [reportType, setReportType] = useState('1104报送');
  const [period, setPeriod] = useState('2026-08-31');
  const titleHint = useMemo(() => tab === '配置管理' ? '按报送类型维护长期配置' : '生成与校验记录相互独立，按报送期分别查询', [tab]);
  return <main className="page"><div className="page-title"><div><h1>报送管理</h1><p>{titleHint}</p></div></div><div className="module-tabs" role="tablist">{['报表生成', '报表校验', '配置管理'].map(item => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item}</button>)}</div><div className="workspace"><ReportRail selected={reportType} onSelect={setReportType} /><div className="workspace-content">{tab === '报表生成' && <GenerationPage reportType={reportType} period={period} setPeriod={setPeriod} notify={notify} />}{tab === '报表校验' && <ValidationPage reportType={reportType} period={period} setPeriod={setPeriod} notify={notify} />}{tab === '配置管理' && <ConfigPage reportType={reportType} notify={notify} />}</div></div></main>;
}

export function App() {
  const [activeModule, setActiveModule] = useState('调度管理');
  const [scheduleSection, setScheduleSection] = useState(() => {
    const routes = { '#scheduling-versions': '版本管理', '#scheduling-tasks': '定时调度' };
    return routes[window.location.hash] || 'KETTLE';
  });
  const [toast, setToast] = useState('');
  useEffect(() => { if (!toast) return undefined; const timer = window.setTimeout(() => setToast(''), 2400); return () => window.clearTimeout(timer); }, [toast]);
  const navigate = item => {
    if (item === '报送管理') { setActiveModule(item); window.location.hash = 'report-management'; }
    else setToast(`${item}保持原系统入口，本原型重点展示调度管理`);
  };
  const navigateSchedule = section => {
    const routes = { KETTLE: 'scheduling-kettle', 版本管理: 'scheduling-versions', 定时调度: 'scheduling-tasks' };
    setActiveModule('调度管理');
    setScheduleSection(section);
    window.location.hash = routes[section];
  };
  return <div className="app-shell"><AppHeader activeModule={activeModule} scheduleSection={scheduleSection} onNavigate={navigate} onNavigateSchedule={navigateSchedule} />{activeModule === '报送管理' ? <ReportingManagement notify={setToast} /> : <SchedulingManagement section={scheduleSection} notify={setToast} onNavigate={navigateSchedule} />}{toast && <div className="toast">{toast}</div>}</div>;
}
