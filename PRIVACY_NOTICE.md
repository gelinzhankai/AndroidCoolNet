# 国家反诈中心检测提示

工具按准确包名 `com.hicorenational.antifraud` 检测主用户（user 0）是否安装国家反诈中心，不按应用名称关键词批量匹配。包名与开发者可在[小米应用商店](https://app.mi.com/details?id=com.hicorenational.antifraud)核对。

检测到后，以红色显示以下风险提醒（输出重定向到文件时使用纯文本）：

> 此应用已有多方报告其越权收集设备数据和滥用用户隐私信息，卸载可以减少该应用继续访问设备数据的机会，但无法撤回已经上传的数据，也不能据此保证整台手机安全。

这段提醒概括公开报告中的风险指称，**不是本工具对当前装机版本的技术审计结论**，也不表示已经证明某个版本能绕过 Android 权限模型。申请权限、实际获得权限、实际收集数据及数据用途是不同问题。

公开来源及范围：

- [Turquoise Roof / Tibet Watch，2024 年报告](https://tibetwatch.org/weaponising-big-data-decoding-chinas-digital-surveillance-in-tibet/)：结合 Android 等版本的动态分析与地区访谈，提出数据收集可能超出反诈目的、参与更广泛监控的风险。不能直接外推为所有后续版本均已复现相同行为。
- [CECC，2024 年报告中的相关章节](https://www.govinfo.gov/content/pkg/CHRG-118jhrg55649/pdf/CHRG-118jhrg55649.pdf)：汇总有关访问个人信息、监控网络活动等用途的报道；属于资料汇编，不是本工具开展的独立实验。
- [Open Technology Fund，2022 年安全评估](https://www.opentech.fund/news/chinas-national-anti-fraud-center-security-assessment/)及[原始报告](https://public.opentech.fund/documents/National_AntiFraud_Center.pdf)：指出敏感权限、数据发往私有后端后的用途不确定等问题。研究明确针对 **iOS，未检查 Android**，且存在测试时间、账号和功能访问限制；不能把其潜在风险当作当前 Android 版本已确认的后门或权限绕过。

操作方式：`1` 或直接回车尝试卸载，`2` 保留；未收到输入（EOF）时保留。卸载会删除当前用户下的应用及本地数据，不使用 root，不移除设备管理员或绕过系统限制，不处理其他用户。卸载失败或无法确认结果时记录原因并继续后续安装流程。`--detect-only` 仅检测，不询问或执行卸载。
