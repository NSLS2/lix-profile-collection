## hplc_scan() moved to 25-hplc.py


## Plotting instructions
## Method 1 : Using Best Effort Callback
## enable live table
#bec.enable_table()
## enable plots
#bec.enable_plots()


## add hints for ex:
#ss2.y.hints = {'fields': ['ss2_y', 'ss2_y_user_setpoint']}

## use em1.describe() to find the fields you can use, then choose them with:
#em1.hints = {'fields': ['em1_current1_mean_value', 'em1_current2_mean_value']}

#RE(relative_scan(DETS, ss2.y, -1,1, 10))


## Method 1 : Directly using LiveTable
#bec.disable_table()
bec.disable_plots()
## run RE on LiveTable with all the field names
#RE(relative_scan(DETS, ss2.y, -1,1, 10), LiveTable(['ss2_y', 'ss2_y_user_setpoint']))
