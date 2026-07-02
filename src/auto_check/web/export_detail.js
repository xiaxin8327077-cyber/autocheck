(function attachExportDetail(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.buildExportDetailText = api.buildExportDetailText;
  root.buildProcessingScript = api.buildProcessingScript;
})(typeof globalThis !== "undefined" ? globalThis : this, function buildExportDetailApi() {
  function formatMoney(value) {
    if (value === null || value === undefined || value === "") return "";
    const number = Number(String(value));
    if (!Number.isFinite(number)) return String(value);
    return number.toLocaleString("zh-CN", { maximumFractionDigits: 8 });
  }

  const circledNumbers = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳";
  const HENGTAI_STOCK_MISMATCH_MESSAGE = "衡泰标的不一致请联系衡泰系统处理。";

  function circledIndex(index) {
    if (index >= 1 && index <= circledNumbers.length) return circledNumbers[index - 1];
    return `${index}.`;
  }

  function normalizeSpecificReason(reason) {
    let nextIndex = 1;
    return String(reason || "")
      .split("\n")
      .map((line) => line.replace(/^([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]|\d+\.)/, () => circledIndex(nextIndex++)))
      .join("\n");
  }

  function isNumberedSpecificReason(reason) {
    const text = String(reason || "");
    return circledNumbers.includes(text[0]) || /^\d+\./.test(text);
  }

  function section(item, title) {
    return (item.display_details || []).find((detail) => detail.title === title) || {};
  }

  function rowValue(rows, label) {
    const row = (rows || []).find((candidate) => candidate.label === label);
    return row ? row.value : "";
  }

  function rowValueAny(rows, labels) {
    for (const label of labels) {
      const value = rowValue(rows, label);
      if (value !== "") return value;
    }
    return "";
  }

  function reportAssetTotalValue(rows) {
    return rowValueAny(rows, ["资负报表资产合计", "zf_detail 资产合计"]);
  }

  function specificReasonLine(rows) {
    const reason = rowValue(rows, "具体原因");
    if (!reason) return "";
    const normalized = normalizeSpecificReason(reason);
    if (normalized.includes("\n") || isNumberedSpecificReason(normalized)) {
      return `具体原因：\n${normalized}`;
    }
    return `具体原因：${normalized}`;
  }

  function matchExplanationLine(rows) {
    const message = rowValue(rows, "匹配说明");
    if (!message) return "";
    return `匹配说明：${message}`;
  }

  function accountLines(item) {
    const detail = section(item, "具体差异明细");
    const rows = detail.table?.rows || [];
    if (!rows.length) return [];
    return [
      "命中科目：",
      ...rows.map((row, index) => {
        const code = row[0] || "";
        const name = row[1] || "";
        const tail = row[2] || "";
        const amount = formatMoney(row[3]);
        return `${circledIndex(index + 1)} 科目代码：${code}；科目名称：${name}；科目尾段：${tail}；金额：${amount}`;
      }),
    ];
  }

  function candidateGroupLines(item) {
    const detail = section(item, "候选组合明细");
    const headers = detail.table?.headers || [];
    const rows = detail.table?.rows || [];
    if (!rows.length) return [];
    const grouped = [];
    rows.forEach((row) => {
      const groupName = tableCell(row, headers, "候选组合", 0);
      const groupTotal = tableCell(row, headers, "组内合计", 1);
      let group = grouped.find((item) => item.name === groupName);
      if (!group) {
        group = { name: groupName, total: groupTotal, rows: [] };
        grouped.push(group);
      }
      group.rows.push(row);
    });

    const lines = [];
    grouped.forEach((group) => {
      lines.push(`${group.name}：合计金额 ${formatMoney(group.total)}`);
      group.rows.forEach((row, index) => {
        lines.push(
          `${circledIndex(index + 1)} 科目代码：${tableCell(row, headers, "科目代码", 2)}；科目名称：${tableCell(row, headers, "科目名称", 3)}；科目尾段：${tableCell(row, headers, "科目尾段", 4)}；金额：${formatMoney(tableCell(row, headers, "金额", 5))}`
        );
      });
    });
    return lines;
  }

  function stockMismatchLine(item) {
    const detail = section(item, "标的代码核对");
    const rows = detail.rows || [];
    const name = rowValue(rows, "FA 估值科目名称");
    const faTail = rowValue(rows, "FA 科目尾段代码");
    const amStock = rowValue(rows, "AM 标的代码");
    if (!faTail || !amStock) return "";
    return `标的核对：FA估值科目名称：${name}；FA科目尾段代码：${faTail}；AM标的代码：${amStock}；核查结果：不一致`;
  }

  function amMissingLine(item) {
    const detail = section(item, "AM标的缺失");
    const rows = detail.rows || [];
    const name = rowValue(rows, "FA 估值科目名称");
    const code = rowValue(rows, "FA 估值科目代码");
    const tail = rowValue(rows, "FA 科目尾段代码");
    if (!code && !name) return "";
    return `AM标的缺失：FA估值科目代码：${code}；FA估值科目名称：${name}；FA科目尾段代码：${tail}；核查结果：未匹配到AM资产信息`;
  }

  function projectInvestLine(item) {
    const detail = section(item, "合同投融资余额核对");
    const rows = detail.rows || [];
    const asset = rowValue(rows, "AM 资产名称");
    const stock = rowValue(rows, "AM 标的代码");
    const pact = rowValue(rows, "AM 合同代码");
    const balance = rowValue(rows, "合同投融资余额");
    if (!asset && !pact) return "";
    return `合同投融资核对：AM资产名称：${asset}；AM标的代码：${stock}；AM合同代码：${pact}；合同投融资余额：${formatMoney(balance)}`;
  }

  function sqlValue(value) {
    return String(value ?? "").replace(/'/g, "''");
  }

  function nestedSqlValue(value) {
    return sqlValue(value).replace(/'/g, "''");
  }

  function stockMismatchScript(infoStockCode, valuationStockCode, pactId) {
    const before = sqlValue(infoStockCode);
    const after = sqlValue(valuationStockCode);
    const pact = sqlValue(pactId);
    const updateBefore = nestedSqlValue(infoStockCode);
    const updateAfter = nestedSqlValue(valuationStockCode);
    const updatePact = nestedSqlValue(pactId);

    return [
      "insert",
      "\tinto",
      "\tdata_mangement.data_mangement_dwd(updatekey,",
      "\tupdatetable,",
      "\tupdatecol,",
      "\tupdatevalue_befor,",
      "\tupdatevalue_after,",
      "\tupdatekeyvalue,",
      "\tlogsql,",
      "\tupdatesql,",
      "\tstatus)",
      `values('c_pactid', 'dwd.am_am_pactasset_dwd', 'c_stockcode', '${before}', '${after}', '${pact}',`,
      `'', 'update dwd.am_am_pactasset_dwd set c_stockcode = ''${updateAfter}'' where c_pactid = ''${updatePact}'' and c_stockcode = ''${updateBefore}''', '1');`,
    ].join("\n");
  }

  function isAmDataSource(dataSource) {
    return String(dataSource || "").trim().toLowerCase() === "am";
  }

  function stockMismatchProcessingText(infoStockCode, valuationStockCode, pactId, dataSource) {
    if (!infoStockCode || !valuationStockCode || !pactId) return "";
    if (!isAmDataSource(dataSource)) return HENGTAI_STOCK_MISMATCH_MESSAGE;
    return stockMismatchScript(infoStockCode, valuationStockCode, pactId);
  }

  function numberedProcessingScripts(scripts) {
    const values = (scripts || []).filter(Boolean);
    if (values.length <= 1) return values[0] || "";
    return values.map((script, index) => `${circledIndex(index + 1)} ${script}`).join("\n\n");
  }

  function detailDataByKind(item, kind) {
    return (item.details || [])
      .filter((detail) => detail?.kind === kind)
      .map((detail) => detail.data || {});
  }

  function isStockMismatchReason(value) {
    return ["FA和AM标的不一致", "FA与AM标的不一致"].includes(String(value || ""));
  }

  function tableCell(row, headers, header, fallbackIndex) {
    const index = (headers || []).indexOf(header);
    return row[index >= 0 ? index : fallbackIndex] || "";
  }

  function assetMissingRefinementProcessingScripts(item) {
    const rawRows = detailDataByKind(item, "asset_missing_refinement")
      .flatMap((data) => Array.isArray(data.rows) ? data.rows : []);
    if (rawRows.length) {
      return rawRows
        .map((row) => {
          if (!isStockMismatchReason(row.check_result) && !isStockMismatchReason(row.reason)) return "";
          return stockMismatchProcessingText(
            row.am_stock_code,
            row.account_tail,
            row.pact_id,
            row.data_source ?? row.c_datasource
          );
        })
        .filter(Boolean);
    }

    const detail = section(item, "资产缺失细分");
    const headers = detail.table?.headers || [];
    const rows = detail.table?.rows || [];
    return rows
      .map((row) => {
        const checkResult = tableCell(row, headers, "核查结果", 7);
        const reason = tableCell(row, headers, "原因", 11);
        if (!isStockMismatchReason(checkResult) && !isStockMismatchReason(reason)) return "";
        const valuationStockCode = tableCell(row, headers, "科目尾段", 4);
        const infoStockCode = tableCell(row, headers, "AM标的代码", 9);
        const pactId = tableCell(row, headers, "AM合同代码", 10);
        return stockMismatchProcessingText(infoStockCode, valuationStockCode, pactId, "");
      })
      .filter(Boolean);
  }

  function buildProcessingScript(item) {
    const refinementScripts = assetMissingRefinementProcessingScripts(item);
    if (refinementScripts.length) return numberedProcessingScripts(refinementScripts);

    const rawScripts = detailDataByKind(item, "fa_am")
      .map((data) => stockMismatchProcessingText(
        data.am_stock_code,
        data.fa_tail_code,
        data.pact_id,
        data.data_source ?? data.c_datasource
      ))
      .filter(Boolean);
    if (rawScripts.length) return numberedProcessingScripts(rawScripts);

    const detail = section(item, "标的代码核对");
    const rows = detail.rows || [];
    const infoStockCode = rowValue(rows, "AM 标的代码");
    const valuationStockCode = rowValue(rows, "FA 科目尾段代码");
    const pactId = rowValue(rows, "AM 合同代码");
    return numberedProcessingScripts([stockMismatchProcessingText(infoStockCode, valuationStockCode, pactId, "")]);
  }

  function propertyRightInvestLines(item, rows) {
    const finalRows = rows || [];
    const detail = section(item, "财产权合同投融资核对");
    if (!detail.title) return [];
    const tableRows = detail.table?.rows || [];
    const lines = [
      `1541财产权核对：估值金额合计=${formatMoney(rowValue(finalRows, "估值1541科目金额合计"))}，AM合同投融资余额合计=${formatMoney(rowValue(finalRows, "AM合同投融资余额合计"))}，差异=${formatMoney(rowValue(finalRows, "投融资-估值差异合计"))}`,
    ];
    if (tableRows.length) {
      lines.push("合同明细：");
      tableRows.forEach((row, index) => {
        lines.push(
          `${circledIndex(index + 1)} 科目代码：${row[0] || ""}；科目名称：${row[1] || ""}；合同代码：${row[2] || ""}；估值金额：${formatMoney(row[3])}；AM合同投融资余额：${formatMoney(row[4])}；差异值：${formatMoney(row[5])}`
        );
      });
    }
    return lines;
  }

  function assetDifferenceRefinementLines(item, rows) {
    const finalRows = rows || [];
    const detail = section(item, "资产差异细分");
    if (!detail.title) return [];
    const tableRows = detail.table?.rows || [];
    const faTotal = rowValueAny(finalRows, ["资产差异FA科目余额合计", "合同FA科目余额合计"]);
    const businessTotal = rowValueAny(finalRows, [
      "资产差异DM证券余额/AM投融资余额/存续回购业务表金额合计",
      "资产差异DM证券/AM/业务表金额合计",
      "资产差异AM/业务表金额合计",
      "合同AM投融资余额合计",
    ]);
    const differenceTotal = rowValueAny(finalRows, ["资产差异金额合计", "合同差异合计"]);
    const lines = [
      `资产差异细分核对：FA科目余额合计=${formatMoney(faTotal)}，DM证券余额/AM投融资余额/存续回购业务表金额合计=${formatMoney(businessTotal)}，差异=${formatMoney(differenceTotal)}`,
    ];
    if (tableRows.length) {
      lines.push("资产差异明细：");
      tableRows.forEach((row) => {
        lines.push(assetDifferenceDetailLine(row));
      });
    }
    return lines;
  }

  function assetDifferenceDetailLine(row) {
    const index = row[0] || "";
    const identifier = assetDifferenceIdentifier(row);
    return [
      `${index} 资产类型：${row[1] || ""}`,
      `资产名称：${row[2] || ""}`,
      `${identifier.label}：${identifier.value}`,
      `FA科目余额：${formatMoney(row[5])}`,
      `${assetDifferenceAmountLabel(row)}：${formatMoney(row[6])}`,
      `差异值：${formatMoney(row[7])}`,
    ].join("；");
  }

  function assetDifferenceIdentifier(row) {
    const identifier = row[4] || "";
    const assetType = row[1] || "";
    const checkTable = row[8] || "";
    if (assetType === "债券" || checkTable === "dm.fa_security_balance_zgxg_dm") {
      return { label: "证券代码", value: identifier || "无" };
    }
    return { label: "合同代码", value: identifier || "无" };
  }

  function assetDifferenceAmountLabel(row) {
    const assetType = row[1] || "";
    const checkTable = row[8] || "";
    if (assetType === "债券" || checkTable === "dm.fa_security_balance_zgxg_dm") {
      return "DM证券余额";
    }
    if (assetType === "逆回购" || checkTable === "ass_man_reg.ex_pledge_back") {
      return "存续回购业务表金额";
    }
    return "AM投融资余额";
  }

  function receivedTrustLine(rows) {
    return `实收核对：c1000实收本金余额=${formatMoney(rowValue(rows, "c1000 实收本金余额"))}，FA 4001科目余额=${formatMoney(rowValue(rows, "FA 4001 科目余额"))}，差异=${formatMoney(rowValue(rows, "4001-c1000 差异"))}`;
  }

  function taTotalMismatchLine(item) {
    const detail = section(item, "TA汇总核对");
    const rows = detail.rows || [];
    const dmTotal = rowValue(rows, "DM TA 份额余额+待结转收益");
    const dwsTotal = rowValue(rows, "DWS TA 份额余额+待结转收益");
    const difference = rowValue(rows, "DM-DWS 差异");
    if (!dmTotal && !dwsTotal && !difference) return "";
    return `TA汇总核对：DM=${formatMoney(dmTotal)}，DWS=${formatMoney(dwsTotal)}，差异=${formatMoney(difference)}`;
  }

  function taBlankClientTypeLines(item) {
    const detail = section(item, "DM TA客户类型为空");
    const rows = detail.rows || [];
    const tableRows = detail.table?.rows || [];
    const lines = [];
    const total = rowValue(rows, "客户类型为空金额合计");
    if (total) {
      lines.push(`客户类型为空：合计=${formatMoney(total)}`);
    }
    if (tableRows.length) {
      lines.push("客户类型明细：");
      tableRows.forEach((row, index) => {
        const pact = row[0] || "";
        const clientName = row[1] || "";
        const clientKind = row[2] || "-";
        const clientKindIndex = row[3] || "-";
        const spvType = row[4] || "-";
        const amount = row[7] || "";
        lines.push(
          `${circledIndex(index + 1)} 合同编号：${pact}；客户名称：${clientName}；客户类型：${clientKind}；客户类型明细：${clientKindIndex}；SPV类型：${spvType}；金额：${formatMoney(amount)}`
        );
      });
    }
    return lines;
  }

  function judgementBasisLines(item) {
    const lines = [];
    for (const detail of item.display_details || []) {
      for (const row of detail.rows || []) {
        if (row.label === "判断依据" && row.value) {
          lines.push(`${row.label}：${row.value}`);
        }
      }
    }
    return lines;
  }

  function buildExportDetailText(item) {
    if ((item.difference_reason || "") === "暂无法确定") {
      const finalSection = section(item, "最终判断结果");
      const rows = finalSection.rows || [];
      const lines = [];
      const specificLine = specificReasonLine(rows);
      if (specificLine) lines.push(specificLine);
      const matchLine = matchExplanationLine(rows);
      if (matchLine) lines.push(matchLine);
      lines.push(...candidateGroupLines(item));
      lines.push(...judgementBasisLines(item));
      return lines.join("\n");
    }

    const finalSection = section(item, "最终判断结果");
    const rows = finalSection.rows || [];
    const lines = [`差异类型：${item.difference_reason || ""}`];
    const specificLine = specificReasonLine(rows);
    if (specificLine) lines.push(specificLine);
    const matchLine = matchExplanationLine(rows);
    if (matchLine) lines.push(matchLine);

    const reasonParts = String(item.difference_reason || "")
      .split(/\s*\+\s*/)
      .filter(Boolean);
    const hasReason = (reason) => reasonParts.includes(reason);
    const hasAssetReason = ["资产缺失", "资产重复", "资产差异"].some(hasReason);
    const hasReceivedTrustReason = ["实收本金差异", "实收本金缺失", "实收本金重复"].some(hasReason);
    const hasLiabilityReason = ["负债及权益科目差异", "负债及权益科目缺失", "负债及权益科目重复"].some(hasReason);

    if (hasAssetReason) {
      lines.push(
        `资产核对：资负报表资产=${formatMoney(reportAssetTotalValue(rows))}，估值表资产=${formatMoney(rowValue(rows, "估值表资产合计"))}，差异=${formatMoney(rowValue(rows, "资产差异金额"))}`,
      );
      const accounts = accountLines(item);
      if (accounts.length) lines.push(...accounts);
      const stockLine = stockMismatchLine(item);
      if (stockLine) lines.push(stockLine);
      const missingLine = amMissingLine(item);
      if (missingLine) lines.push(missingLine);
      const investLine = projectInvestLine(item);
      if (investLine) lines.push(investLine);
      const propertyRightLines = propertyRightInvestLines(item, rows);
      if (propertyRightLines.length) lines.push(...propertyRightLines);
      const assetDifferenceLines = assetDifferenceRefinementLines(item, rows);
      if (assetDifferenceLines.length) lines.push(...assetDifferenceLines);
      lines.push(...candidateGroupLines(item));
    }

    if (hasReceivedTrustReason) {
      lines.push(receivedTrustLine(rows));
      const totalLine = taTotalMismatchLine(item);
      if (totalLine) lines.push(totalLine);
      lines.push(...taBlankClientTypeLines(item));
    }

    if (hasLiabilityReason) {
      const mainDifference = rowValue(rows, "主差异");
      const receivedTrustGap = rowValue(rows, "实收差额") || rowValue(rows, "4001-c1000 差异");
      const residualGap = rowValue(rows, "剩余差额") || rowValue(rows, "资产端解释后剩余差额");
      if (mainDifference || receivedTrustGap || residualGap) {
        lines.push(
          `剩余差额核对：主差异=${formatMoney(mainDifference)}，实收差额=${formatMoney(receivedTrustGap)}，剩余差额=${formatMoney(residualGap)}`,
        );
      }
      lines.push(
        `权益核对：范围=${rowValue(rows, "核对范围")}，命中方式=${rowValue(rows, "命中方式")}，命中金额=${formatMoney(rowValue(rows, "命中金额"))}`,
      );
      const accounts = accountLines(item);
      if (accounts.length) lines.push(...accounts);
      lines.push(...candidateGroupLines(item));
    }

    if (hasAssetReason || hasReceivedTrustReason || hasLiabilityReason) {
      return lines.join("\n");
    }

    return "";
  }

  return { buildExportDetailText, buildProcessingScript };
});
