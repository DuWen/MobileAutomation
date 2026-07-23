/**
 * ECharts 图表初始化脚本
 * 方案C详细设计文档 - 技术栈雷达对比图
 */

/**
 * 初始化技术栈雷达对比图
 * 对比 LangGraph / LangChain / AutoGen / CrewAI 五个维度
 */
function initRadarChart() {
  const chartDom = document.getElementById('radar-tech-stack');
  if (!chartDom) return;

  const chart = echarts.init(chartDom);

  const option = {
    color: ['#4B3FE3', '#22A5F7', '#F59E0B', '#22C55E'],
    legend: {
      data: ['LangGraph', 'LangChain', 'AutoGen', 'CrewAI'],
      bottom: 10,
      textStyle: { fontFamily: 'WorkSans, sans-serif', fontSize: 12 }
    },
    tooltip: {
      trigger: 'item',
      textStyle: { fontFamily: 'WorkSans, sans-serif' }
    },
    radar: {
      indicator: [
        { name: '多Agent编排', max: 10 },
        { name: '状态管理', max: 10 },
        { name: '调试可观测性', max: 10 },
        { name: '生产就绪度', max: 10 },
        { name: '生态丰富度', max: 10 }
      ],
      shape: 'polygon',
      splitNumber: 5,
      axisName: {
        color: '#6b7280',
        fontSize: 13,
        fontFamily: 'WorkSans, sans-serif'
      },
      splitLine: {
        lineStyle: { color: '#e5e7eb' }
      },
      splitArea: {
        areaStyle: {
          color: ['#fff', '#f5f6fa', '#fff', '#f5f6fa', '#fff']
        }
      },
      axisLine: {
        lineStyle: { color: '#e5e7eb' }
      }
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: [9, 9, 8, 8, 6],
          name: 'LangGraph',
          areaStyle: { opacity: 0.12 }
        },
        {
          value: [5, 4, 6, 7, 9],
          name: 'LangChain',
          areaStyle: { opacity: 0.12 }
        },
        {
          value: [8, 5, 5, 5, 5],
          name: 'AutoGen',
          areaStyle: { opacity: 0.12 }
        },
        {
          value: [7, 4, 5, 6, 6],
          name: 'CrewAI',
          areaStyle: { opacity: 0.12 }
        }
      ]
    }]
  };

  chart.setOption(option);

  // 响应窗口大小变化
  window.addEventListener('resize', function () {
    chart.resize();
  });
}

/**
 * 初始化成本估算柱状图
 */
function initCostChart() {
  const chartDom = document.getElementById('cost-bar-chart');
  if (!chartDom) return;

  const chart = echarts.init(chartDom);

  const option = {
    color: ['#4B3FE3', '#22A5F7'],
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      textStyle: { fontFamily: 'WorkSans, sans-serif' },
      formatter: function (params) {
        let result = params[0].name + '<br/>';
        params.forEach(function (p) {
          result += p.marker + ' ' + p.seriesName + ': $' + p.value + '<br/>';
        });
        return result;
      }
    },
    legend: {
      data: ['月度成本', '季度成本'],
      bottom: 10,
      textStyle: { fontFamily: 'WorkSans, sans-serif', fontSize: 12 }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '15%',
      top: '10%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: ['LLM Token', '设备资源', '基础设施', '人力维护'],
      axisLabel: { fontFamily: 'WorkSans, sans-serif', fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        fontFamily: 'WorkSans, sans-serif',
        fontSize: 11,
        formatter: '${value}'
      }
    },
    series: [
      {
        name: '月度成本',
        type: 'bar',
        data: [1200, 800, 400, 1500]
      },
      {
        name: '季度成本',
        type: 'bar',
        data: [3600, 2400, 1200, 4500]
      }
    ]
  };

  chart.setOption(option);
  window.addEventListener('resize', function () { chart.resize(); });
}

// 页面加载完成后初始化所有图表
document.addEventListener('DOMContentLoaded', function () {
  initRadarChart();
  initCostChart();
});