// pages/index/index.js
const app = getApp()

Page({
    data: {
        appName: '',
        count: 0,
        showMessage: false,
        items: [
            { id: 1, name: 'WXML 模板测试' },
            { id: 2, name: 'WXSS 样式测试' },
            { id: 3, name: '配置文件测试' }
        ]
    },

    onLoad() {
        this.setData({
            appName: app.globalData.appName
        })
    },

    onAddCount() {
        this.setData({
            count: this.data.count + 1
        })
    },

    onToggleMessage() {
        this.setData({
            showMessage: !this.data.showMessage
        })
    }
})
