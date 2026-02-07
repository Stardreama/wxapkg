// pages/about/about.js
const app = getApp()

Page({
    data: {
        version: '',
        features: [
            'WXML 模板还原',
            'WXSS 样式还原 (含 rpx)',
            'app.json 配置还原',
            '页面级配置还原',
            '数据绑定语法',
            'wx:if 条件渲染',
            'wx:for 列表渲染'
        ]
    },

    onLoad() {
        this.setData({
            version: app.globalData.version
        })
    }
})
